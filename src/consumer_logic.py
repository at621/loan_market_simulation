"""Consumer decision logic for loan selection."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ConsumerDecisionEngine:
    """Handles consumer loan decisions based on utility maximization."""

    def calculate_consumer_utility(
        self,
        consumer: pd.Series,
        bank: pd.Series,
        rate_score: float,
        portfolio_history: List[Dict[str, float]]
    ) -> float:
        """
        Calculate utility for a consumer-bank pair considering portfolio history.
        
        Args:
            consumer: Consumer data (rate_sensitivity, weights, etc.)
            bank: Bank data (image_score, execution_speed, etc.)
            rate_score: Normalized rate competitiveness score (0-1)
            portfolio_history: List of dicts with bank_id -> portfolio_balance for each round
        
        Returns:
            Utility score for this consumer-bank combination
        """
        # Apply rate sensitivity
        adjusted_rate_score = rate_score ** (1 + consumer["rate_sensitivity"])
        
        # Calculate portfolio stability factor
        stability_score = self._calculate_portfolio_stability(bank["id"], portfolio_history)
        
        # Base utility from existing factors
        base_utility = (
            consumer["rate_weight"] * adjusted_rate_score +
            consumer["image_weight"] * bank["image_score"] +
            consumer["speed_weight"] * bank["execution_speed"]
        )
        
        # Add portfolio stability as a small additional factor (up to 10% boost/penalty)
        portfolio_weight = 0.1
        total_utility = base_utility * (1 + portfolio_weight * (stability_score - 0.5))
        
        return total_utility
    
    def _calculate_portfolio_stability(
        self, 
        bank_id: str, 
        portfolio_history: List[Dict[str, float]]
    ) -> float:
        """
        Calculate portfolio stability score (0-1) based on historical portfolio balances.
        
        Args:
            bank_id: Bank identifier
            portfolio_history: List of portfolio balance snapshots by round
            
        Returns:
            Stability score where 1.0 = very stable, 0.0 = very unstable
        """
        if len(portfolio_history) < 2:
            return 0.5  # Neutral for insufficient history
        
        # Get this bank's portfolio balance history
        balances = []
        for round_data in portfolio_history:
            balance = round_data.get(bank_id, 0.0)
            balances.append(balance)
        
        if not balances or all(b == 0 for b in balances):
            return 0.0  # No portfolio = very risky
        
        # Remove zeros for meaningful calculations
        non_zero_balances = [b for b in balances if b > 0]
        if len(non_zero_balances) < 2:
            return 0.2  # Mostly zero balances = risky
        
        # Calculate stability metrics
        mean_balance = sum(non_zero_balances) / len(non_zero_balances)
        
        # Growth trend (positive growth = good)
        if len(non_zero_balances) >= 2:
            recent_balance = non_zero_balances[-1]
            earlier_balance = non_zero_balances[0]
            growth_factor = min(2.0, recent_balance / earlier_balance) if earlier_balance > 0 else 1.0
            growth_score = min(1.0, growth_factor / 2.0)  # Cap at 1.0
        else:
            growth_score = 0.5
        
        # Volatility (lower volatility = more stable)
        if len(non_zero_balances) >= 3:
            # Calculate coefficient of variation
            variance = sum((b - mean_balance) ** 2 for b in non_zero_balances) / len(non_zero_balances)
            std_dev = variance ** 0.5
            cv = std_dev / mean_balance if mean_balance > 0 else float('inf')
            volatility_score = max(0.0, 1.0 - min(1.0, cv))  # Lower CV = higher score
        else:
            volatility_score = 0.5
        
        # Size factor (larger portfolios = perceived as safer)
        # Normalize against typical portfolio sizes (100M baseline)
        size_factor = min(1.0, mean_balance / 100_000_000)
        
        # Combine factors
        stability_score = (
            0.4 * growth_score +
            0.3 * volatility_score +
            0.3 * size_factor
        )
        
        return max(0.0, min(1.0, stability_score))

    def allocate_consumers(
        self,
        consumers: pd.DataFrame,
        market_rates: Dict[str, int],
        banks: pd.DataFrame,
        active_bank_ids: List[str],
        reservation_utility: float,
        portfolio_history: Optional[List[Dict[str, float]]] = None,
        bank_capacities: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Optional[str]]:
        """
        Allocate consumers to banks based on utility maximization with capacity constraints.
        Uses waterfall allocation: consumers with highest utility get priority, and when
        their preferred bank is full, they get allocated to their next choice.

        Args:
            bank_capacities: Dict mapping bank_id to available lending capacity (in dollars)

        Returns:
            Dict mapping consumer_id to bank_id (or None if no loan taken)
        """
        if not active_bank_ids:
            logger.warning("No active banks - no loans will be allocated")
            return {c_id: None for c_id in consumers["id"]}

        # Default to empty portfolio history if not provided
        if portfolio_history is None:
            portfolio_history = []

        # Default to unlimited capacity if not provided
        if bank_capacities is None:
            bank_capacities = {bank_id: float('inf') for bank_id in active_bank_ids}

        # Convert market rates to DataFrame for vectorization
        active_banks = banks[banks["id"].isin(active_bank_ids)].copy()
        active_banks["offered_rate"] = active_banks["id"].map(market_rates)

        # Calculate rate scores for all banks
        min_rate = active_banks["offered_rate"].min()
        max_rate = active_banks["offered_rate"].max()

        if min_rate == max_rate:
            # All rates are the same
            active_banks["rate_score"] = 0.5
        else:
            active_banks["rate_score"] = (max_rate - active_banks["offered_rate"]) / (
                max_rate - min_rate
            )

        # Calculate utilities for all consumer-bank pairs and prepare for waterfall allocation
        consumer_preferences = []

        for _, consumer in consumers.iterrows():
            # Calculate utility for each bank using the separate utility function
            utilities = []

            for _, bank in active_banks.iterrows():
                utility = self.calculate_consumer_utility(
                    consumer, bank, bank["rate_score"], portfolio_history
                )
                utilities.append({"bank_id": bank["id"], "utility": utility})

            # Sort banks by utility for this consumer (highest first)
            utilities.sort(key=lambda x: x["utility"], reverse=True)
            
            # Only consider banks that meet reservation utility
            valid_utilities = [u for u in utilities if u["utility"] >= reservation_utility]
            
            if valid_utilities:
                # Store consumer with their bank preferences and their best utility score
                consumer_preferences.append({
                    "consumer_id": consumer["id"],
                    "loan_size": consumer["loan_size"],
                    "bank_preferences": valid_utilities,
                    "best_utility": valid_utilities[0]["utility"]
                })
            else:
                # Consumer will not take any loan
                consumer_preferences.append({
                    "consumer_id": consumer["id"],
                    "loan_size": consumer["loan_size"],
                    "bank_preferences": [],
                    "best_utility": 0.0
                })

        # Sort consumers by their best utility score (highest first) - most satisfied consumers get priority
        consumer_preferences.sort(key=lambda x: x["best_utility"], reverse=True)

        # Initialize tracking
        remaining_capacities = bank_capacities.copy()
        allocations = {}

        # Waterfall allocation
        for consumer_data in consumer_preferences:
            consumer_id = consumer_data["consumer_id"]
            loan_size = consumer_data["loan_size"]
            bank_preferences = consumer_data["bank_preferences"]
            
            allocated = False
            
            # Try to allocate to preferred banks in order
            for bank_pref in bank_preferences:
                bank_id = bank_pref["bank_id"]
                
                # Check if bank has sufficient capacity
                if remaining_capacities[bank_id] >= loan_size:
                    # Allocate to this bank
                    allocations[consumer_id] = bank_id
                    remaining_capacities[bank_id] -= loan_size
                    allocated = True
                    break
            
            # If no bank could accommodate, consumer gets no loan
            if not allocated:
                allocations[consumer_id] = None

        # Log allocation summary
        allocated_count = sum(1 for v in allocations.values() if v is not None)
        logger.info(
            f"Allocated {allocated_count} of {len(consumers)} consumers to banks"
        )

        # Log bank allocation counts and capacity utilization
        bank_counts = {}
        for bank_id in active_bank_ids:
            count = sum(1 for v in allocations.values() if v == bank_id)
            bank_counts[bank_id] = count
            if count > 0:
                capacity_used = bank_capacities[bank_id] - remaining_capacities[bank_id]
                capacity_remaining = remaining_capacities[bank_id]
                logger.info(f"Bank {bank_id}: {count} new loans, "
                           f"${capacity_used:,.0f} capacity used, "
                           f"${capacity_remaining:,.0f} remaining")

        return allocations

    def calculate_market_metrics(
        self, allocations: Dict[str, Optional[str]], consumers: pd.DataFrame
    ) -> Dict:
        """Calculate market-level metrics from allocations."""
        total_consumers = len(allocations)
        allocated_consumers = sum(1 for v in allocations.values() if v is not None)

        # Calculate total volume by bank
        bank_volumes = {}
        bank_counts = {}

        for consumer_id, bank_id in allocations.items():
            if bank_id is not None:
                consumer = consumers[consumers["id"] == consumer_id].iloc[0]

                if bank_id not in bank_volumes:
                    bank_volumes[bank_id] = 0
                    bank_counts[bank_id] = 0

                bank_volumes[bank_id] += consumer["loan_size"]
                bank_counts[bank_id] += 1

        return {
            "total_consumers": total_consumers,
            "allocated_consumers": allocated_consumers,
            "allocation_rate": (
                allocated_consumers / total_consumers if total_consumers > 0 else 0
            ),
            "bank_volumes": bank_volumes,
            "bank_counts": bank_counts,
            "unmet_demand": total_consumers - allocated_consumers,
        }
