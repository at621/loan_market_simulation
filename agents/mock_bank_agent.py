"""Mock bank AI agent for testing without API keys."""

import asyncio
import logging
import random
from typing import Dict, Any

from src.models import BankDecision

logger = logging.getLogger(__name__)


class MockBankAgent:
    """Mock AI agent that makes rate decisions using simple heuristics."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize mock bank agent."""
        self.config = config
        self.max_retries = config.get('max_retries', 3)
        self.use_fallback = config.get('use_fallback_on_error', True)
    
    async def make_decision(self, bank_info: Dict, market_context: Dict) -> BankDecision:
        """Make a rate decision using mock logic."""
        # Simulate some processing time
        await asyncio.sleep(0.1)
        
        # Get parameters
        strategy = bank_info['strategy']
        equity = bank_info['current_equity']
        last_profit = bank_info['last_profit']
        last_roe = bank_info['last_roe']
        cost_of_funds = bank_info['cost_of_funds_bps']
        portfolio_balance = bank_info['portfolio_balance']
        active_loans = bank_info['active_loan_count']
        last_new_loans = bank_info['last_new_loan_count']
        
        # Calculate equity ratio for risk assessment
        equity_ratio = equity / (portfolio_balance + 1)  # Avoid division by zero
        
        # Mock decision logic based on comprehensive bank state
        if equity_ratio < 0.05:  # Very low equity - survival mode
            base_rate = cost_of_funds + 250
            reasoning = f"Survival mode: equity only {equity_ratio:.1%} of portfolio, need high margins"
        elif equity_ratio < 0.08:  # Low equity - be conservative
            base_rate = cost_of_funds + 200
            reasoning = f"Conservative pricing: low equity ratio {equity_ratio:.1%}, last ROE {last_roe:.1%}"
        elif strategy == "Grow":
            if last_profit > 0 and last_roe > 0.1:
                # Aggressive pricing when profitable
                base_rate = cost_of_funds + 100
                reasoning = f"Aggressive growth: strong ROE {last_roe:.1%}, gained {last_new_loans} loans last round"
            elif last_profit > 0:
                # Moderate growth
                base_rate = cost_of_funds + 150
                reasoning = f"Moderate growth: profitable but ROE {last_roe:.1%} below target"
            else:
                # Conservative after losses
                base_rate = cost_of_funds + 200
                reasoning = f"Recovery mode: last loss ${last_profit:,.0f}, {active_loans} active loans"
        else:  # Maintain strategy
            if last_roe > 0.15:  # Very profitable
                base_rate = cost_of_funds + 180
                reasoning = f"Maintain profits: excellent ROE {last_roe:.1%}, {active_loans} loans"
            elif last_profit > 0:
                base_rate = cost_of_funds + 160
                reasoning = f"Stable pricing: positive ROE {last_roe:.1%}, maintaining position"
            else:
                base_rate = cost_of_funds + 220
                reasoning = f"Defensive pricing: loss ${last_profit:,.0f}, focus on margins"
        
        # Market competition adjustment
        if len(market_context.get('market_history', [])) > 0:
            last_round = market_context['market_history'][-1]
            market_avg = sum(last_round.offered_rates.values()) / len(last_round.offered_rates)
            
            # Slight adjustment based on market rates
            if strategy == "Grow" and base_rate > market_avg + 50:
                base_rate = market_avg + 25  # Stay competitive for growth
                reasoning += f", adjusted to compete with market avg {market_avg:.0f} bps"
        
        # Add some randomness
        rate_variation = random.randint(-15, 15)
        final_rate = base_rate + rate_variation
        
        # Ensure rate is within bounds
        final_rate = max(100, min(1000, final_rate))
        
        # Predict outcome based on rate and bank position
        if final_rate < cost_of_funds + 120:
            expected_outcome = f"Target 12-18% market share, moderate margins"
        elif final_rate < cost_of_funds + 180:
            expected_outcome = f"Target 8-12% market share, balanced approach"
        else:
            expected_outcome = f"Target 5-10% market share, focus on profitability"
        
        logger.info(f"Mock Bank {bank_info['bank_id']} decision: {final_rate} bps - {reasoning[:100]}...")
        
        return BankDecision(
            bank_id=bank_info['bank_id'],
            rate_bps=final_rate,
            reasoning=reasoning,
            expected_outcome=expected_outcome
        )