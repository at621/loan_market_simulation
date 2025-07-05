"""Bank AI agent for making strategic rate decisions."""

import asyncio
import logging
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json
import re

from src.models import BankDecision

logger = logging.getLogger(__name__)


class BankAgent:
    """AI agent that makes rate decisions for banks."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize bank agent with AI configuration."""
        self.config = config
        try:
            self.llm = ChatOpenAI(
                model_name=config.get("model", "gpt-4"),
                temperature=config.get("temperature", 0.7),
                request_timeout=config.get("timeout_seconds", 30),
            )
        except Exception as e:
            logger.error(f"Failed to initialize BankAgent LLM: {e}", exc_info=True)
            print(f"ERROR: Failed to initialize Bank AI agent: {e}")
            print(
                f"Check your OpenAI API key and model configuration: {config.get('model', 'gpt-4')}"
            )
            raise
        self.max_retries = config.get("max_retries", 3)
        self.use_fallback = config.get("use_fallback_on_error", True)

    async def make_decision(
        self, bank_info: Dict, market_context: Dict
    ) -> BankDecision:
        """Make a rate decision for a bank given its context."""
        prompt = self._build_prompt(bank_info, market_context)

        for attempt in range(self.max_retries):
            try:
                response = await self._get_llm_decision(prompt)
                decision = self._parse_decision(response, bank_info["bank_id"])

                if decision.validate():
                    return decision
                else:
                    logger.warning(
                        f"Invalid decision from LLM: {decision.rate_bps} bps"
                    )

            except Exception as e:
                logger.error(
                    f"Bank {bank_info['bank_id']} decision attempt {attempt + 1} failed: {e}",
                    exc_info=True,
                )
                print(
                    f"WARNING: Bank {bank_info['bank_id']} AI decision failed (attempt {attempt + 1}): {e}"
                )
                if attempt == self.max_retries - 1:
                    print(
                        f"ERROR: Bank {bank_info['bank_id']} AI agent failed after {self.max_retries} attempts!"
                    )
                    raise

        raise Exception(
            f"Bank {bank_info['bank_id']} failed to get valid decision after {self.max_retries} retries"
        )

    def _build_prompt(self, bank_info: Dict, market_context: Dict) -> str:
        """Build the prompt for the bank agent."""
        # Calculate derived metrics
        remaining_rounds = (
            market_context["total_rounds"] - market_context["current_round"] + 1
        )

        # Build historical performance data
        historical_data = self._build_historical_data(bank_info, market_context)

        # Get market statistics
        if market_context["market_history"]:
            last_round = market_context["market_history"][-1]
            avg_rate = sum(last_round.offered_rates.values()) / len(
                last_round.offered_rates
            )

            # Calculate market share
            total_volume = sum(last_round.new_volumes.values())
            bank_volume = last_round.new_volumes.get(bank_info["bank_id"], 0)
            market_share = (bank_volume / total_volume * 100) if total_volume > 0 else 0

            # Find struggling banks
            struggling_banks = [
                bid for bid, profit in last_round.profits.items() if profit < 0
            ]

            # Format competitor strategies
            competitor_strategies = []
            for bid, strategy in market_context["all_bank_strategies"].items():
                if bid != bank_info["bank_id"]:
                    equity = last_round.equities.get(bid, 0)
                    status = (
                        "BANKRUPT"
                        if bid in last_round.bankruptcies
                        else f"${equity:,.0f} equity"
                    )
                    competitor_strategies.append(
                        f"- {bid}: {strategy} strategy ({status})"
                    )
        else:
            # First round
            avg_rate = 500  # Use initial rate
            market_share = 10  # Assume equal share
            struggling_banks = []
            competitor_strategies = [
                f"- {bid}: {strategy} strategy"
                for bid, strategy in market_context["all_bank_strategies"].items()
                if bid != bank_info["bank_id"]
            ]

        # Check bankruptcy condition (portfolio volume below 30% of original)
        bankruptcy_warning = self._check_bankruptcy_risk(bank_info, market_context)

        # Build the prompt
        prompt = f"""You are the CEO of {bank_info['bank_id']} in a competitive loan market simulation.

YOUR OBJECTIVE: Maximize cumulative profit over the remaining {remaining_rounds} rounds.

YOUR BANK'S PROFILE:
- Strategy: {bank_info['strategy']} (publicly known)
- Current Equity: ${bank_info['current_equity']:,.0f}
- Portfolio Balance: ${bank_info['portfolio_balance']:,.0f}
- Last Round Profit: ${bank_info['last_profit']:,.0f}
- Last Round ROE: {bank_info['last_roe']:.1%}
- Image Score: {bank_info['image_score']:.2f}
- Execution Speed: {bank_info['execution_speed']:.2f}

COST STRUCTURE:
- Cost of Funds: {bank_info['cost_of_funds_bps']} bps
- Operating Cost per Loan: ${bank_info['operating_cost_per_loan']:,.0f}

MARKET INTELLIGENCE:
- Current Round: {market_context['current_round']} of {market_context['total_rounds']}
- Average Market Rate Last Round: {avg_rate:.0f} bps
- Your Market Share: {market_share:.1f}%
- Banks with Negative Profit: {len(struggling_banks)}
- Consumer Reservation Utility: {market_context['behavior_params']['reservation_utility']}

{bankruptcy_warning}

HISTORICAL PERFORMANCE DATA:
{historical_data}

COMPETITOR STRATEGIES:
{chr(10).join(competitor_strategies)}

STRATEGIC ANALYSIS:
"""

        # Add context-specific guidance
        if bank_info["current_equity"] < bank_info["portfolio_balance"] * 0.05:
            prompt += """
WARNING: Your equity is critically low. You must prioritize survival over growth.
- Break-even rate needed: approximately {} bps
- Consider defensive pricing to maintain profitability
""".format(
                bank_info["cost_of_funds_bps"] + 100
            )

        elif bank_info["strategy"] == "Grow" and market_share < 15:
            prompt += """
As a GROW strategy bank, you should aim to gain market share.
- Current share is below target
- Consider aggressive pricing if equity buffer allows
- Monitor competitor bankruptcies for opportunities
"""

        elif bank_info["last_roe"] > 0.15:
            prompt += """
Your bank is highly profitable. Consider:
- Whether to maintain margins or expand share
- Risk of attracting aggressive competition
- Long-term sustainability of current position
"""

        prompt += """

CONSUMER BEHAVIOR:
- 100 consumers, each takes at most 1 loan per round
- Consumers value: low rates (weighted by sensitivity), bank image, execution speed
- Average loan size: $100,000

DECISION REQUIRED:
Set your interest rate for this round. Consider:
1. Your survival constraints (equity > 0)
2. Competitive dynamics and likely responses
3. Trade-off between volume and margin
4. Your publicly known strategy creates expectations

Provide your decision in the following format:
RATE: [your rate in basis points, integer between 100-1000]
REASONING: [2-3 sentences explaining your strategic logic]
EXPECTED: [brief prediction of market share and profit impact]

Make your decision:"""

        return prompt

    async def _get_llm_decision(self, prompt: str) -> str:
        """Get decision from LLM."""
        messages = [
            SystemMessage(
                content="You are a strategic bank CEO making pricing decisions."
            ),
            HumanMessage(content=prompt),
        ]

        response = await self.llm.agenerate([messages])
        return response.generations[0][0].text

    def _parse_decision(self, response: str, bank_id: str) -> BankDecision:
        """Parse the LLM response into a BankDecision object."""
        # Extract rate
        rate_match = re.search(r"RATE:\s*(\d+)", response, re.IGNORECASE)
        if not rate_match:
            raise ValueError("Could not parse rate from response")
        rate_bps = int(rate_match.group(1))

        # Extract reasoning
        reasoning_match = re.search(
            r"REASONING:\s*(.+?)(?=EXPECTED:|$)", response, re.IGNORECASE | re.DOTALL
        )
        reasoning = (
            reasoning_match.group(1).strip()
            if reasoning_match
            else "No reasoning provided"
        )

        # Extract expected outcome
        expected_match = re.search(
            r"EXPECTED:\s*(.+?)$", response, re.IGNORECASE | re.DOTALL
        )
        expected = (
            expected_match.group(1).strip()
            if expected_match
            else "No prediction provided"
        )

        return BankDecision(
            bank_id=bank_id,
            rate_bps=rate_bps,
            reasoning=reasoning,
            expected_outcome=expected,
        )

    def _build_historical_data(self, bank_info: Dict, market_context: Dict) -> str:
        """Build historical performance data table for the bank agent."""
        if not market_context.get("market_history"):
            return "No historical data available (first round)."
        
        bank_id = bank_info["bank_id"]
        history = market_context["market_history"]
        
        # Build table header
        lines = ["Round | ROE (%) | Rate (bps) | Volume ($M) | Market Share (%)"]
        lines.append("------|---------|-----------|-------------|----------------")
        
        for i, round_data in enumerate(history, 1):
            # Get this bank's data for the round
            roe = round_data.profits.get(bank_id, 0) / max(1, round_data.equities.get(bank_id, 1)) * 100
            rate = round_data.offered_rates.get(bank_id, 0)
            volume = round_data.new_volumes.get(bank_id, 0) / 1_000_000  # Convert to millions
            
            # Calculate market share
            total_volume = sum(round_data.new_volumes.values())
            market_share = (round_data.new_volumes.get(bank_id, 0) / total_volume * 100) if total_volume > 0 else 0
            
            lines.append(f"  {i:2d}  | {roe:7.1f} | {rate:9d} | {volume:11.1f} | {market_share:14.1f}")
        
        return "\n".join(lines)

    def _check_bankruptcy_risk(self, bank_info: Dict, market_context: Dict) -> str:
        """Check if bank is at risk of bankruptcy due to volume decline."""
        if not market_context.get("market_history"):
            return ""
        
        bank_id = bank_info["bank_id"]
        history = market_context["market_history"]
        
        # Get original volume (first round)
        if not history:
            return ""
        
        original_volume = history[0].new_volumes.get(bank_id, 0)
        if original_volume == 0:
            return ""
        
        # Get current volume (last round)
        current_volume = history[-1].new_volumes.get(bank_id, 0)
        
        # Calculate percentage of original
        volume_ratio = current_volume / original_volume if original_volume > 0 else 0
        
        if volume_ratio < 0.3:
            return f"""
🚨 BANKRUPTCY WARNING: Your loan volume has dropped to {volume_ratio:.1%} of original levels!
- Original volume: ${original_volume:,.0f}
- Current volume: ${current_volume:,.0f}
- Risk: Below 30% threshold triggers bankruptcy
- Action needed: Aggressive recovery strategy required
"""
        elif volume_ratio < 0.5:
            return f"""
⚠️  VOLUME ALERT: Your loan volume is {volume_ratio:.1%} of original levels.
- Risk of approaching 30% bankruptcy threshold
- Consider defensive pricing or market share recovery tactics
"""
        
        return ""
