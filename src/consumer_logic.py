"""Consumer decision logic for loan selection."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ConsumerDecisionEngine:
    """Handles consumer loan decisions based on utility maximization."""
    
    def allocate_consumers(self, 
                          consumers: pd.DataFrame,
                          market_rates: Dict[str, int],
                          banks: pd.DataFrame,
                          active_bank_ids: List[str],
                          reservation_utility: float) -> Dict[str, Optional[str]]:
        """
        Allocate consumers to banks based on utility maximization.
        
        Returns:
            Dict mapping consumer_id to bank_id (or None if no loan taken)
        """
        if not active_bank_ids:
            logger.warning("No active banks - no loans will be allocated")
            return {c_id: None for c_id in consumers['id']}
        
        # Convert market rates to DataFrame for vectorization
        active_banks = banks[banks['id'].isin(active_bank_ids)].copy()
        active_banks['offered_rate'] = active_banks['id'].map(market_rates)
        
        # Calculate rate scores for all banks
        min_rate = active_banks['offered_rate'].min()
        max_rate = active_banks['offered_rate'].max()
        
        if min_rate == max_rate:
            # All rates are the same
            active_banks['rate_score'] = 0.5
        else:
            active_banks['rate_score'] = (max_rate - active_banks['offered_rate']) / (max_rate - min_rate)
        
        # Calculate utilities for all consumer-bank pairs
        allocations = {}
        
        for _, consumer in consumers.iterrows():
            # Calculate utility for each bank
            utilities = []
            
            for _, bank in active_banks.iterrows():
                # Apply rate sensitivity
                adjusted_rate_score = bank['rate_score'] ** (1 + consumer['rate_sensitivity'])
                
                # Calculate weighted utility
                utility = (
                    consumer['rate_weight'] * adjusted_rate_score +
                    consumer['image_weight'] * bank['image_score'] +
                    consumer['speed_weight'] * bank['execution_speed']
                )
                
                utilities.append({
                    'bank_id': bank['id'],
                    'utility': utility
                })
            
            # Find best utility
            best_bank = max(utilities, key=lambda x: x['utility'])
            
            # Check reservation utility
            if best_bank['utility'] >= reservation_utility:
                allocations[consumer['id']] = best_bank['bank_id']
            else:
                allocations[consumer['id']] = None
        
        # Log allocation summary
        allocated_count = sum(1 for v in allocations.values() if v is not None)
        logger.info(f"Allocated {allocated_count} of {len(consumers)} consumers to banks")
        
        # Log bank allocation counts
        bank_counts = {}
        for bank_id in active_bank_ids:
            count = sum(1 for v in allocations.values() if v == bank_id)
            bank_counts[bank_id] = count
            if count > 0:
                logger.info(f"Bank {bank_id}: {count} new loans")
        
        return allocations
    
    def calculate_market_metrics(self, 
                               allocations: Dict[str, Optional[str]],
                               consumers: pd.DataFrame) -> Dict:
        """Calculate market-level metrics from allocations."""
        total_consumers = len(allocations)
        allocated_consumers = sum(1 for v in allocations.values() if v is not None)
        
        # Calculate total volume by bank
        bank_volumes = {}
        bank_counts = {}
        
        for consumer_id, bank_id in allocations.items():
            if bank_id is not None:
                consumer = consumers[consumers['id'] == consumer_id].iloc[0]
                
                if bank_id not in bank_volumes:
                    bank_volumes[bank_id] = 0
                    bank_counts[bank_id] = 0
                
                bank_volumes[bank_id] += consumer['loan_size']
                bank_counts[bank_id] += 1
        
        return {
            'total_consumers': total_consumers,
            'allocated_consumers': allocated_consumers,
            'allocation_rate': allocated_consumers / total_consumers if total_consumers > 0 else 0,
            'bank_volumes': bank_volumes,
            'bank_counts': bank_counts,
            'unmet_demand': total_consumers - allocated_consumers
        }