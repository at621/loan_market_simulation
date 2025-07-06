"""
Profit calculator for bank agents to simulate future profits based on pricing decisions.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging
from dataclasses import dataclass

from src.consumer_logic import ConsumerDecisionEngine
from src.financial_calculator import FinancialCalculator

logger = logging.getLogger(__name__)


@dataclass
class ProfitProjection:
    """Results from profit calculation scenario."""
    scenario_rate: int  # Rate in basis points
    projected_new_loans: int
    projected_loan_volume: float
    projected_revenue: float
    projected_costs: float
    projected_profit: float
    projected_roe: float
    market_share: float
    capacity_utilized: float


class BankProfitCalculator:
    """Calculator for projecting bank profits under different pricing scenarios."""
    
    def __init__(self):
        self.consumer_engine = ConsumerDecisionEngine()
        self.financial_calc = FinancialCalculator()
        
    def calculate_profit_scenarios(
        self,
        bank_info: Dict,
        market_context: Dict,
        scenario_rates: List[int],
        consumers: List,
        num_rounds_ahead: int = 1
    ) -> List[ProfitProjection]:
        """
        Calculate profit projections for different rate scenarios.
        
        Args:
            bank_info: Current bank information
            market_context: Current market state
            scenario_rates: List of rates (in bps) to test
            consumers: List of consumers for this round
            num_rounds_ahead: Number of rounds to project (default: 1)
            
        Returns:
            List of ProfitProjection objects for each scenario
        """
        projections = []
        
        # Get current market rates (other banks' rates stay constant)
        current_market_rates = market_context.get("current_market_rates", {})
        current_bank_id = bank_info["bank_id"]
        
        # Extract bank financial information
        current_equity = bank_info["current_equity"]
        current_portfolio_balance = bank_info["portfolio_balance"]
        cost_of_funds_bps = bank_info["cost_of_funds_bps"]
        operating_cost_per_loan = bank_info["operating_cost_per_loan"]
        leverage_limit = bank_info.get("leverage_limit", 10)
        
        for test_rate in scenario_rates:
            try:
                projection = self._calculate_single_scenario(
                    bank_info=bank_info,
                    test_rate=test_rate,
                    market_rates=current_market_rates,
                    consumers=consumers,
                    num_rounds_ahead=num_rounds_ahead
                )
                projections.append(projection)
                
            except Exception as e:
                logger.warning(f"Failed to calculate scenario for rate {test_rate}bps: {e}")
                # Create a zero projection for failed scenarios
                projections.append(ProfitProjection(
                    scenario_rate=test_rate,
                    projected_new_loans=0,
                    projected_loan_volume=0.0,
                    projected_revenue=0.0,
                    projected_costs=0.0,
                    projected_profit=0.0,
                    projected_roe=0.0,
                    market_share=0.0,
                    capacity_utilized=0.0
                ))
                
        return projections
    
    def _calculate_single_scenario(
        self,
        bank_info: Dict,
        test_rate: int,
        market_rates: Dict[str, int],
        consumers: List,
        num_rounds_ahead: int
    ) -> ProfitProjection:
        """Calculate projection for a single rate scenario."""
        
        current_bank_id = bank_info["bank_id"]
        current_equity = bank_info["current_equity"]
        current_portfolio_balance = bank_info["portfolio_balance"]
        cost_of_funds_bps = bank_info["cost_of_funds_bps"]
        operating_cost_per_loan = bank_info["operating_cost_per_loan"]
        leverage_limit = bank_info.get("leverage_limit", 10)
        
        # Create hypothetical market rates with our test rate
        scenario_market_rates = market_rates.copy()
        scenario_market_rates[current_bank_id] = test_rate
        
        # Calculate bank capacities
        bank_capacities = {}
        for bank_id, rate in scenario_market_rates.items():
            if bank_id == current_bank_id:
                # Use our bank's actual capacity
                max_portfolio = current_equity * leverage_limit
                available_capacity = max(0, max_portfolio - current_portfolio_balance)
                bank_capacities[bank_id] = available_capacity
            else:
                # Assume other banks have some capacity (simplified)
                # In a real scenario, we'd need market intelligence about competitor capacities
                bank_capacities[bank_id] = 100_000_000  # $100M default capacity
        
        # Simulate consumer allocation with our test rate
        allocations = self.consumer_engine.allocate_consumers_to_banks(
            consumers=consumers,
            bank_rates=scenario_market_rates,
            bank_image_scores={bank_id: 0.7 for bank_id in scenario_market_rates.keys()},  # Simplified
            bank_execution_speeds={bank_id: 0.8 for bank_id in scenario_market_rates.keys()},  # Simplified
            bank_capacities=bank_capacities
        )
        
        # Extract results for our bank
        our_allocations = [c for c in allocations if c.get("chosen_bank") == current_bank_id]
        
        projected_new_loans = len(our_allocations)
        projected_loan_volume = sum(c.get("loan_size", 100_000) for c in our_allocations)
        
        # Calculate market share
        total_allocations = len([c for c in allocations if c.get("chosen_bank") is not None])
        market_share = projected_new_loans / max(1, total_allocations)
        
        # Calculate capacity utilization
        max_portfolio = current_equity * leverage_limit
        available_capacity = max(0, max_portfolio - current_portfolio_balance)
        capacity_utilized = projected_loan_volume / max(1, available_capacity) if available_capacity > 0 else 0
        
        # Project financials over multiple rounds
        projected_profit = 0.0
        projected_revenue = 0.0
        projected_costs = 0.0
        
        for round_num in range(num_rounds_ahead):
            # Revenue from new loans (interest income)
            # Assume loans are held for the full period
            round_revenue = projected_loan_volume * (test_rate / 10000)  # Convert bps to decimal
            
            # Costs
            funding_cost = projected_loan_volume * (cost_of_funds_bps / 10000)
            operating_costs = projected_new_loans * operating_cost_per_loan
            round_costs = funding_cost + operating_costs
            
            # Profit for this round
            round_profit = round_revenue - round_costs
            
            projected_revenue += round_revenue
            projected_costs += round_costs
            projected_profit += round_profit
        
        # Calculate ROE (annualized if projecting multiple rounds)
        if current_equity > 0:
            roe_factor = 1.0 if num_rounds_ahead == 1 else num_rounds_ahead
            projected_roe = (projected_profit / current_equity) / roe_factor
        else:
            projected_roe = 0.0
        
        return ProfitProjection(
            scenario_rate=test_rate,
            projected_new_loans=projected_new_loans,
            projected_loan_volume=projected_loan_volume,
            projected_revenue=projected_revenue,
            projected_costs=projected_costs,
            projected_profit=projected_profit,
            projected_roe=projected_roe,
            market_share=market_share,
            capacity_utilized=capacity_utilized
        )
    
    def find_optimal_rate(
        self,
        bank_info: Dict,
        market_context: Dict,
        consumers: List,
        rate_range: Tuple[int, int] = (300, 800),
        rate_step: int = 10,
        num_rounds_ahead: int = 1
    ) -> ProfitProjection:
        """
        Find the rate that maximizes projected profit.
        
        Args:
            bank_info: Current bank information
            market_context: Current market state
            consumers: List of consumers for this round
            rate_range: (min_rate, max_rate) in basis points
            rate_step: Step size for rate testing
            num_rounds_ahead: Number of rounds to project
            
        Returns:
            ProfitProjection for the optimal rate
        """
        min_rate, max_rate = rate_range
        scenario_rates = list(range(min_rate, max_rate + 1, rate_step))
        
        projections = self.calculate_profit_scenarios(
            bank_info=bank_info,
            market_context=market_context,
            scenario_rates=scenario_rates,
            consumers=consumers,
            num_rounds_ahead=num_rounds_ahead
        )
        
        # Find the rate with maximum profit
        optimal_projection = max(projections, key=lambda p: p.projected_profit)
        
        return optimal_projection
    
    def format_scenarios_for_prompt(
        self,
        projections: List[ProfitProjection],
        top_n: int = 5
    ) -> str:
        """
        Format profit projections for inclusion in LLM prompt.
        
        Args:
            projections: List of profit projections
            top_n: Number of top scenarios to include
            
        Returns:
            Formatted string for LLM prompt
        """
        if not projections:
            return "No profit projections available."
        
        # Sort by profit (descending)
        sorted_projections = sorted(projections, key=lambda p: p.projected_profit, reverse=True)
        top_projections = sorted_projections[:top_n]
        
        lines = ["PROFIT PROJECTIONS (if competitors keep current rates):"]
        lines.append("")
        
        for i, proj in enumerate(top_projections, 1):
            lines.append(f"  Scenario {i}: {proj.scenario_rate} bps")
            lines.append(f"    New Loans: {proj.projected_new_loans:,}")
            lines.append(f"    Loan Volume: ${proj.projected_loan_volume:,.0f}")
            lines.append(f"    Projected Profit: ${proj.projected_profit:,.0f}")
            lines.append(f"    Projected ROE: {proj.projected_roe:.1%}")
            lines.append(f"    Market Share: {proj.market_share:.1%}")
            lines.append(f"    Capacity Used: {proj.capacity_utilized:.1%}")
            lines.append("")
        
        # Add summary of optimal rate
        optimal = max(projections, key=lambda p: p.projected_profit)
        lines.append(f"OPTIMAL RATE: {optimal.scenario_rate} bps (${optimal.projected_profit:,.0f} profit)")
        
        return "\n".join(lines)