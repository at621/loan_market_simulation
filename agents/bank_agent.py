"""Bank AI agent for making strategic rate decisions."""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json
import re
import pandas as pd

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
        self.decision_logs = []  # Store prompts and decisions for detailed logging

    async def make_decision(
        self, bank_info: Dict, market_context: Dict
    ) -> BankDecision:
        """Make a rate decision for a bank given its context."""
        prompt = self._build_prompt(bank_info, market_context)
        
        # Log the decision details
        decision_log = {
            "bank_id": bank_info["bank_id"],
            "round": market_context["current_round"],
            "prompt": prompt,
            "response": None,
            "decision": None,
            "timestamp": None
        }

        for attempt in range(self.max_retries):
            try:
                response = await self._get_llm_decision(prompt)
                decision = self._parse_decision(response, bank_info["bank_id"])

                if decision.validate():
                    # Store the successful decision log
                    decision_log["response"] = response
                    decision_log["decision"] = {
                        "rate_bps": decision.rate_bps,
                        "reasoning": decision.reasoning,
                        "expected_outcome": decision.expected_outcome,
                        "previous_decision_evaluation": decision.previous_decision_evaluation,
                        "previous_decision_score": decision.previous_decision_score
                    }
                    decision_log["timestamp"] = pd.Timestamp.now().isoformat()
                    self.decision_logs.append(decision_log)
                    
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
                    # Log the failed attempt
                    decision_log["response"] = f"ERROR: {str(e)}"
                    decision_log["timestamp"] = pd.Timestamp.now().isoformat()
                    self.decision_logs.append(decision_log)
                    
                    print(
                        f"ERROR: Bank {bank_info['bank_id']} AI agent failed after {self.max_retries} attempts!"
                    )
                    raise

        raise Exception(
            f"Bank {bank_info['bank_id']} failed to get valid decision after {self.max_retries} retries"
        )

    def _get_previous_decision(self, bank_id: str, current_round: int) -> Optional[Dict]:
        """Get the previous round's decision for this bank."""
        if current_round <= 1:
            return None
            
        for log in reversed(self.decision_logs):
            if log.get("bank_id") == bank_id and log.get("round") == current_round - 1:
                return log
        return None
    
    def _build_decision_history(self, bank_id: str, current_round: int) -> str:
        """Build a comprehensive decision history for this bank."""
        if current_round <= 1:
            return "No previous decisions (Round 1)."
        
        # Get all previous decisions for this bank
        bank_decisions = []
        for log in self.decision_logs:
            if log.get("bank_id") == bank_id and log.get("round", 0) < current_round:
                bank_decisions.append(log)
        
        # Sort by round
        bank_decisions.sort(key=lambda x: x.get("round", 0))
        
        if not bank_decisions:
            return "No previous decisions recorded."
        
        lines = []
        lines.append("YOUR PREVIOUS DECISIONS HISTORY:")
        lines.append("")
        
        for i, decision_log in enumerate(bank_decisions):
            round_num = decision_log.get("round", 0)
            decision = decision_log.get("decision", {})
            
            lines.append(f"Round {round_num}:")
            lines.append(f"  • Rate Set: {decision.get('rate_bps', 'N/A')} bps")
            lines.append(f"  • Reasoning: {decision.get('reasoning', 'No reasoning recorded')}")
            lines.append(f"  • Expected Outcome: {decision.get('expected_outcome', 'No expectation recorded')}")
            
            # Show self-evaluation from the NEXT round (if available)
            next_round_log = None
            for next_log in self.decision_logs:
                if (next_log.get("bank_id") == bank_id and 
                    next_log.get("round", 0) == round_num + 1):
                    next_round_log = next_log
                    break
            
            if next_round_log and next_round_log.get("decision", {}).get("previous_decision_evaluation"):
                next_decision = next_round_log.get("decision", {})
                evaluation = next_decision.get("previous_decision_evaluation", "")
                score = next_decision.get("previous_decision_score", "N/A")
                lines.append(f"  • Self-Evaluation (Next Round): {evaluation}")
                lines.append(f"  • Self-Score: {score}/10")
            else:
                lines.append(f"  • Self-Evaluation: Not yet evaluated")
                lines.append(f"  • Self-Score: Not yet scored")
            
            lines.append("")
        
        return "\n".join(lines)

    def _build_prompt(self, bank_info: Dict, market_context: Dict) -> str:
        """Build the prompt for the bank agent."""
        # Calculate derived metrics
        remaining_rounds = (
            market_context["total_rounds"] - market_context["current_round"] + 1
        )

        # Build historical performance data
        historical_data = self._build_historical_data(bank_info, market_context)
        
        # Build decision history for this bank
        decision_history = self._build_decision_history(bank_info['bank_id'], market_context['current_round'])

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

🏦 YOU ARE BANK: {bank_info['bank_id']} (IMPORTANT: Remember this is YOUR bank ID)

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

COMPETITOR STRATEGIES:
{chr(10).join(competitor_strategies)}

COMPREHENSIVE MARKET DATA (Your bank marked with *):
{historical_data}

{decision_history}

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

"""
        
        # Add previous decision evaluation section if not round 1
        previous_decision = self._get_previous_decision(bank_info['bank_id'], market_context['current_round'])
        if previous_decision and previous_decision.get('decision'):
            prev_dec = previous_decision['decision']
            
            # Calculate objective score
            actual_metrics = {
                'market_share': bank_info.get('last_market_share', 0),
                'profit': bank_info['last_profit'],
                'roe': bank_info['last_roe']
            }
            
            score_analysis = self._calculate_objective_score(
                prev_dec.get('expected_outcome', ''),
                actual_metrics
            )
            
            # Store for later use in parsing
            self._last_score_analysis = score_analysis
            
            prompt += f"""
PREVIOUS ROUND SELF-EVALUATION:
Your previous decision (Round {market_context['current_round'] - 1}):
- Rate set: {prev_dec.get('rate_bps', 'N/A')} bps
- Reasoning: {prev_dec.get('reasoning', 'No reasoning recorded')}
- Expected outcome: {prev_dec.get('expected_outcome', 'No expectation recorded')}

Actual outcome:
- Your actual market share: {bank_info.get('last_market_share', 0):.1f}%
- Your actual profit: ${bank_info['last_profit']/1e6:.1f}M
- Your actual ROE: {bank_info['last_roe']:.1%}

OBJECTIVE SCORING ANALYSIS:"""
            
            if score_analysis['expected']['market_share'] is not None:
                prompt += f"""
- Predicted market share: {score_analysis['expected']['market_share']:.1f}% | Actual: {actual_metrics['market_share']:.1f}%"""
            else:
                prompt += """
- No market share prediction found"""
                
            if score_analysis['expected']['profit'] is not None:
                prompt += f"""
- Predicted profit: ${score_analysis['expected']['profit']/1e6:.1f}M | Actual: ${actual_metrics['profit']/1e6:.1f}M"""
            
            prompt += f"""
- Objective accuracy score: {score_analysis['score']}/10
- Score reasoning: {score_analysis['reasoning']}

Based on this objective analysis, please:
1. Acknowledge your prediction accuracy
2. Explain what factors you missed or correctly anticipated
3. Accept the objective score of {score_analysis['score']}/10
"""
        
        prompt += """
DECISION REQUIRED:
Set your interest rate for this round. Consider:
1. Your survival constraints (equity > 0)
2. Competitive dynamics and likely responses
3. Trade-off between volume and margin
4. Your publicly known strategy creates expectations
5. Lessons from your previous decisions

Provide your decision in the following format:
"""
        
        if previous_decision:
            prompt += """EVALUATION: [2-3 sentences acknowledging the objective score and explaining what you learned]
SCORE: """ + str(score_analysis['score']) + """ (objective score based on prediction accuracy)
"""
        
        prompt += """RATE: [your rate in basis points, integer between 100-1000]
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
        # Extract evaluation (if present)
        evaluation_match = re.search(
            r"EVALUATION:\s*(.+?)(?=SCORE:|RATE:|$)", response, re.IGNORECASE | re.DOTALL
        )
        evaluation = (
            evaluation_match.group(1).strip()
            if evaluation_match
            else None
        )
        
        # Extract score (if present) - now it's the objective score
        score_match = re.search(r"SCORE:\s*(\d+)", response, re.IGNORECASE)
        score = int(score_match.group(1)) if score_match else None
        
        # If score wasn't found and we have a previous decision, calculate it objectively
        if score is None and hasattr(self, '_last_score_analysis'):
            score = self._last_score_analysis.get('score', None)
        
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
            previous_decision_evaluation=evaluation,
            previous_decision_score=score,
        )

    def _build_historical_data(self, bank_info: Dict, market_context: Dict) -> str:
        """Build comprehensive historical market data tables for the bank agent."""
        if not market_context.get("market_history"):
            return "No historical data available (first round)."
        
        bank_id = bank_info["bank_id"]
        history = market_context["market_history"]
        
        # Get all bank IDs from the market history
        all_bank_ids = set()
        for round_data in history:
            all_bank_ids.update(round_data.offered_rates.keys())
        all_bank_ids = sorted(list(all_bank_ids))
        
        # Build comprehensive market intelligence tables
        lines = []
        
        # 1. ROE by Round (%) - Highlight your bank
        lines.append("## MARKET INTELLIGENCE - ROE BY ROUND (%)")
        lines.append("")
        header = "| Round |" + "".join(f" {bid:>6} |" for bid in all_bank_ids)
        lines.append(header)
        separator = "|-------|" + "".join("--------|" for _ in all_bank_ids)
        lines.append(separator)
        
        for i, round_data in enumerate(history, 1):
            row_data = [f"|   {i:2d}  |"]
            for bid in all_bank_ids:
                equity = round_data.equities.get(bid, 1)
                profit = round_data.profits.get(bid, 0)
                roe = (profit / max(1, equity)) * 100
                
                # Highlight your bank with asterisk
                if bid == bank_id:
                    row_data.append(f" {roe:5.1f}*|")
                else:
                    row_data.append(f" {roe:5.1f} |")
            lines.append("".join(row_data))
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 2. Interest Rates by Round (bps)
        lines.append("## INTEREST RATES BY ROUND (bps)")
        lines.append("")
        lines.append(header)
        lines.append(separator)
        
        for i, round_data in enumerate(history, 1):
            row_data = [f"|   {i:2d}  |"]
            for bid in all_bank_ids:
                rate = round_data.offered_rates.get(bid, 0)
                
                # Highlight your bank with asterisk
                if bid == bank_id:
                    row_data.append(f" {rate:4d}* |")
                else:
                    row_data.append(f" {rate:4d}  |")
            lines.append("".join(row_data))
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 3. Profit by Round ($M)
        lines.append("## PROFIT BY ROUND ($M)")
        lines.append("")
        lines.append(header)
        lines.append(separator)
        
        for i, round_data in enumerate(history, 1):
            row_data = [f"|   {i:2d}  |"]
            for bid in all_bank_ids:
                profit = round_data.profits.get(bid, 0) / 1_000_000  # Convert to millions
                
                # Highlight your bank with asterisk
                if bid == bank_id:
                    row_data.append(f" {profit:5.1f}*|")
                else:
                    row_data.append(f" {profit:5.1f} |")
            lines.append("".join(row_data))
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 4. Equity by Round ($M)
        lines.append("## EQUITY BY ROUND ($M)")
        lines.append("")
        lines.append(header)
        lines.append(separator)
        
        for i, round_data in enumerate(history, 1):
            row_data = [f"|   {i:2d}  |"]
            for bid in all_bank_ids:
                equity = round_data.equities.get(bid, 0) / 1_000_000  # Convert to millions
                
                # Highlight your bank with asterisk
                if bid == bank_id:
                    row_data.append(f" {equity:5.1f}*|")
                else:
                    row_data.append(f" {equity:5.1f} |")
            lines.append("".join(row_data))
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 5. Market Share by Round (%)
        lines.append("## MARKET SHARE BY ROUND (%)")
        lines.append("")
        lines.append(header)
        lines.append(separator)
        
        for i, round_data in enumerate(history, 1):
            row_data = [f"|   {i:2d}  |"]
            total_volume = sum(round_data.new_volumes.values())
            
            for bid in all_bank_ids:
                volume = round_data.new_volumes.get(bid, 0)
                market_share = (volume / total_volume * 100) if total_volume > 0 else 0
                
                # Highlight your bank with asterisk
                if bid == bank_id:
                    row_data.append(f" {market_share:5.1f}*|")
                else:
                    row_data.append(f" {market_share:5.1f} |")
            lines.append("".join(row_data))
        
        lines.append("")
        lines.append("* = YOUR BANK")
        
        return "\n".join(lines)

    def _calculate_objective_score(self, expected_outcome: str, actual_metrics: Dict) -> Dict[str, Any]:
        """
        Calculate objective self-assessment score based on prediction accuracy.
        
        Args:
            expected_outcome: The bank's prediction from previous round
            actual_metrics: Dict with actual_market_share, actual_profit, actual_roe
            
        Returns:
            Dict with score (1-10) and breakdown of accuracy metrics
        """
        import re
        
        # Extract expected values from the prediction text
        expected_values = {
            'market_share': None,
            'profit': None,
            'roe': None
        }
        
        # Try to extract market share prediction (e.g., "15-20%", "15%", "targeting 15%")
        market_share_patterns = [
            r'(\d+)-(\d+)%\s*(?:market\s*share|share)',
            r'(?:targeting|expecting|aiming\s*for|around)\s*(\d+)%?\s*(?:market\s*share|share)',
            r'(\d+)%\s*(?:market\s*share|share)',
            r'(?:market\s*share|share).*?(\d+)-(\d+)%',
            r'(?:market\s*share|share).*?(\d+)%'
        ]
        
        for pattern in market_share_patterns:
            match = re.search(pattern, expected_outcome, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:  # Range
                    expected_values['market_share'] = (float(groups[0]) + float(groups[1])) / 2
                else:  # Single value
                    expected_values['market_share'] = float(groups[0])
                break
        
        # Try to extract profit prediction (e.g., "$2M", "$2.5 million", "profit of 2M")
        profit_patterns = [
            r'\$(\d+(?:\.\d+)?)\s*[Mm](?:illion)?',
            r'profit.*?(\d+(?:\.\d+)?)\s*[Mm](?:illion)?',
            r'(\d+(?:\.\d+)?)\s*[Mm](?:illion)?\s*(?:in\s*)?profit'
        ]
        
        for pattern in profit_patterns:
            match = re.search(pattern, expected_outcome, re.IGNORECASE)
            if match:
                expected_values['profit'] = float(match.group(1)) * 1_000_000  # Convert to dollars
                break
        
        # Try to extract ROE prediction (e.g., "15% ROE", "ROE of 15%")
        roe_patterns = [
            r'(\d+(?:\.\d+)?)\s*%\s*ROE',
            r'ROE.*?(\d+(?:\.\d+)?)\s*%',
            r'return\s*on\s*equity.*?(\d+(?:\.\d+)?)\s*%'
        ]
        
        for pattern in roe_patterns:
            match = re.search(pattern, expected_outcome, re.IGNORECASE)
            if match:
                expected_values['roe'] = float(match.group(1))
                break
        
        # Calculate accuracy scores
        scores = {}
        
        # Market share accuracy (0-100% scale, max error of 20% = score 0)
        if expected_values['market_share'] is not None and actual_metrics.get('market_share') is not None:
            error = abs(expected_values['market_share'] - actual_metrics['market_share'])
            scores['market_share_score'] = max(0, 10 - (error / 2))  # 2% error = -1 point
        
        # Profit accuracy (relative error)
        if expected_values['profit'] is not None and actual_metrics.get('profit') is not None:
            if actual_metrics['profit'] > 0:
                relative_error = abs(expected_values['profit'] - actual_metrics['profit']) / actual_metrics['profit']
                scores['profit_score'] = max(0, 10 - (relative_error * 20))  # 50% error = 0 score
            else:
                # If actual profit is negative, check if prediction was also negative
                if expected_values['profit'] < 0:
                    scores['profit_score'] = 7  # Good for predicting loss
                else:
                    scores['profit_score'] = 3  # Poor for missing the loss
        
        # ROE accuracy (percentage point difference)
        if expected_values['roe'] is not None and actual_metrics.get('roe') is not None:
            error = abs(expected_values['roe'] - actual_metrics['roe'] * 100)  # Convert actual to percentage
            scores['roe_score'] = max(0, 10 - (error / 2))  # 2 percentage points = -1 point
        
        # Calculate overall score (weighted average of available scores)
        available_scores = [v for k, v in scores.items() if v is not None]
        if available_scores:
            overall_score = sum(available_scores) / len(available_scores)
        else:
            # If no quantitative predictions were made, give a neutral score
            overall_score = 5.0
        
        return {
            'score': round(overall_score),
            'expected': expected_values,
            'actual': actual_metrics,
            'component_scores': scores,
            'reasoning': self._generate_score_reasoning(expected_values, actual_metrics, scores)
        }

    def _generate_score_reasoning(self, expected: Dict, actual: Dict, scores: Dict) -> str:
        """Generate reasoning for the objective score."""
        reasons = []
        
        if scores.get('market_share_score') is not None:
            if expected['market_share'] is not None and actual['market_share'] is not None:
                diff = actual['market_share'] - expected['market_share']
                if abs(diff) < 2:
                    reasons.append(f"Excellent market share prediction (expected {expected['market_share']:.1f}%, actual {actual['market_share']:.1f}%)")
                elif abs(diff) < 5:
                    reasons.append(f"Good market share prediction (expected {expected['market_share']:.1f}%, actual {actual['market_share']:.1f}%)")
                else:
                    reasons.append(f"Poor market share prediction (expected {expected['market_share']:.1f}%, actual {actual['market_share']:.1f}%)")
        
        if scores.get('profit_score') is not None:
            if expected['profit'] is not None and actual['profit'] is not None:
                exp_str = f"${expected['profit']/1e6:.1f}M"
                act_str = f"${actual['profit']/1e6:.1f}M"
                if scores['profit_score'] >= 8:
                    reasons.append(f"Excellent profit prediction (expected {exp_str}, actual {act_str})")
                elif scores['profit_score'] >= 5:
                    reasons.append(f"Moderate profit prediction (expected {exp_str}, actual {act_str})")
                else:
                    reasons.append(f"Poor profit prediction (expected {exp_str}, actual {act_str})")
        
        if not reasons:
            reasons.append("No quantitative predictions found in expected outcome")
        
        return "; ".join(reasons)

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
    
    def get_decision_logs(self) -> List[Dict]:
        """Get all decision logs for this agent."""
        return self.decision_logs
    
    def clear_decision_logs(self):
        """Clear decision logs (useful between megaruns)."""
        self.decision_logs = []
    
    def format_decision_logs_markdown(self) -> str:
        """Format all decision logs as a detailed markdown document."""
        if not self.decision_logs:
            return "# Bank Decision Logs\n\nNo decisions recorded.\n"
        
        lines = ["# Bank AI Decision Logs", ""]
        lines.append(f"Generated at: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Group logs by round
        logs_by_round = {}
        for log in self.decision_logs:
            round_num = log.get("round", 0)
            if round_num not in logs_by_round:
                logs_by_round[round_num] = []
            logs_by_round[round_num].append(log)
        
        # Format each round
        for round_num in sorted(logs_by_round.keys()):
            lines.append(f"## Round {round_num}")
            lines.append("")
            
            # Sort banks by ID for consistent ordering
            round_logs = sorted(logs_by_round[round_num], key=lambda x: x.get("bank_id", ""))
            
            for log in round_logs:
                bank_id = log.get("bank_id", "Unknown")
                lines.append(f"### Bank {bank_id}")
                lines.append("")
                
                # Timestamp
                if log.get("timestamp"):
                    lines.append(f"**Decision Time:** {log['timestamp']}")
                    lines.append("")
                
                # Prompt section
                lines.append("#### Prompt Sent to AI:")
                lines.append("```")
                lines.append(log.get("prompt", "No prompt recorded"))
                lines.append("```")
                lines.append("")
                
                # Response section
                lines.append("#### AI Response:")
                if log.get("response") and not log["response"].startswith("ERROR:"):
                    lines.append("```")
                    lines.append(log["response"])
                    lines.append("```")
                elif log.get("response"):
                    lines.append(f"⚠️ **Error:** {log['response']}")
                else:
                    lines.append("*No response recorded*")
                lines.append("")
                
                # Decision summary
                if log.get("decision"):
                    decision = log["decision"]
                    lines.append("#### Decision Summary:")
                    
                    # Show self-evaluation if present
                    if decision.get('previous_decision_evaluation'):
                        lines.append("##### Self-Evaluation of Previous Round:")
                        lines.append(f"- **Evaluation:** {decision.get('previous_decision_evaluation', 'N/A')}")
                        lines.append(f"- **Score:** {decision.get('previous_decision_score', 'N/A')}/10")
                        lines.append("")
                    
                    lines.append(f"- **Rate Set:** {decision.get('rate_bps', 'N/A')} bps")
                    lines.append(f"- **Reasoning:** {decision.get('reasoning', 'No reasoning provided')}")
                    lines.append(f"- **Expected Outcome:** {decision.get('expected_outcome', 'No prediction provided')}")
                else:
                    lines.append("#### Decision Summary:")
                    lines.append("*No valid decision made*")
                
                lines.append("")
                lines.append("---")
                lines.append("")
        
        return "\n".join(lines)
