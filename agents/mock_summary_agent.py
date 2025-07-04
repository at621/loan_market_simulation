"""Mock summary agent for testing without API keys."""

import pandas as pd
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class MockSummaryAgent:
    """Mock AI agent that generates simple summaries without LLM calls."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize mock summary agent."""
        self.config = config
    
    async def generate_summary(self, 
                             market_log: List[Dict],
                             portfolio_ledger: pd.DataFrame,
                             banks: pd.DataFrame,
                             config: Dict) -> str:
        """Generate basic summary using simple analysis."""
        
        # Convert market log to DataFrame for analysis
        market_df = pd.DataFrame(market_log)
        
        # Basic analysis
        final_round = market_df[market_df['round'] == market_df['round'].max()]
        
        # Strategy performance
        grow_banks = final_round[final_round['strategy'] == 'Grow']
        maintain_banks = final_round[final_round['strategy'] == 'Maintain']
        
        grow_survivors = grow_banks[grow_banks['bankrupt_flag'] == False]
        maintain_survivors = maintain_banks[maintain_banks['bankrupt_flag'] == False]
        
        # Cumulative profits
        grow_total_profit = market_df[market_df['strategy'] == 'Grow']['profit'].sum()
        maintain_total_profit = market_df[market_df['strategy'] == 'Maintain']['profit'].sum()
        
        # Top performers
        cumulative_profits = market_df.groupby('bank_id')['profit'].sum().sort_values(ascending=False)
        top_3 = cumulative_profits.head(3)
        
        # Rate trends
        avg_rates_by_round = market_df.groupby('round')['offered_rate'].mean()
        
        summary = f"""# Loan Market Simulation Summary (Mock Analysis)

## Strategy Performance

### Grow Strategy Banks
- Survivors: {len(grow_survivors)}/{len(grow_banks)} banks
- Average final equity: ${grow_survivors['equity'].mean():,.0f}
- Total cumulative profit: ${grow_total_profit:,.0f}

### Maintain Strategy Banks  
- Survivors: {len(maintain_survivors)}/{len(maintain_banks)} banks
- Average final equity: ${maintain_survivors['equity'].mean():,.0f}
- Total cumulative profit: ${maintain_total_profit:,.0f}

## Market Dynamics

### Interest Rate Evolution
The average market rate evolved as follows:
{chr(10).join([f"- Round {round}: {rate:.0f} bps" for round, rate in avg_rates_by_round.items()])}

### Top Performers (Cumulative Profit)
{chr(10).join([f"- {bank_id}: ${profit:,.0f}" for bank_id, profit in top_3.items()])}

## Key Insights

1. **Strategy Effectiveness**: {"Grow" if grow_total_profit > maintain_total_profit else "Maintain"} strategy generated higher total profits (${max(grow_total_profit, maintain_total_profit):,.0f} vs ${min(grow_total_profit, maintain_total_profit):,.0f})

2. **Survival Rates**: {"Grow" if len(grow_survivors)/max(len(grow_banks),1) > len(maintain_survivors)/max(len(maintain_banks),1) else "Maintain"} banks had better survival rates

3. **Market Evolution**: Interest rates {"increased" if avg_rates_by_round.iloc[-1] > avg_rates_by_round.iloc[0] else "decreased"} from {avg_rates_by_round.iloc[0]:.0f} to {avg_rates_by_round.iloc[-1]:.0f} bps over the simulation

4. **Competition**: The market saw {len(final_round[final_round['bankrupt_flag'] == True])} bankruptcies out of {len(final_round)} total banks

## Conclusions

This simulation demonstrates the complex dynamics of loan market competition. The results suggest that {"aggressive growth strategies can be profitable but risky" if grow_total_profit > maintain_total_profit else "conservative strategies provide more stable returns"}.

*Note: This is a mock analysis. For deeper insights, run with AI agents enabled.*"""

        logger.info("Generated mock summary")
        return summary