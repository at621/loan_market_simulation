"""
AI agent for extracting lessons learned from simulation results.
"""

import re
import json
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import pandas as pd

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.memory_store import Lesson, BankOutcome, StrategyPattern, MemoryStore
from src.models import Bank, SimulationState

logger = logging.getLogger(__name__)


class LessonsAgent:
    """Agent that extracts lessons and patterns from simulation results."""

    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.3):
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        self.memory_store = MemoryStore()

    async def extract_lessons(
        self,
        state: SimulationState,
        summary_content: str,
        initial_banks: List[Bank],
        config: Dict,
    ) -> Tuple[List[Lesson], List[StrategyPattern], str]:
        """Extract lessons from completed simulation."""
        # Calculate bank outcomes
        bank_outcomes = self._calculate_bank_outcomes(state, initial_banks)

        # Get historical patterns for context
        historical_patterns = self.memory_store.get_strategy_patterns(
            min_observations=3
        )
        similar_lessons = self._get_similar_market_lessons(state)

        # Prepare market conditions summary
        market_conditions = self._summarize_market_conditions(state)

        # Generate lessons using AI
        lessons = await self._generate_lessons(
            summary_content,
            bank_outcomes,
            market_conditions,
            historical_patterns,
            similar_lessons,
        )

        # Extract strategy patterns
        patterns = self._extract_patterns(bank_outcomes, market_conditions)

        # Generate lessons learned markdown
        lessons_md = self._generate_lessons_markdown(
            lessons, patterns, bank_outcomes, market_conditions
        )

        # Store everything in memory
        sim_id = self.memory_store.store_simulation(
            config, 
            config.get("seed", 42),  # Use config seed
            state["current_round"],  # Use current_round from state
            market_conditions
        )
        self.memory_store.store_lessons(sim_id, lessons)
        self.memory_store.store_bank_outcomes(sim_id, bank_outcomes)
        self.memory_store.update_strategy_patterns(patterns)

        return lessons, patterns, lessons_md

    def _calculate_bank_outcomes(
        self, state: SimulationState, initial_banks: List[Bank]
    ) -> List[BankOutcome]:
        """Calculate final outcomes for all banks."""
        outcomes = []

        # Get final round data
        final_banks_df = state["banks"]  # This is a DataFrame
        market_log_df = pd.DataFrame(state["market_log"])

        for initial_bank in initial_banks:
            # Calculate metrics from market log
            bank_data = market_log_df[market_log_df["bank_id"] == initial_bank.id]

            if not bank_data.empty:
                # Calculate market share manually if not in data
                total_volume_by_round = market_log_df.groupby("round")["new_loan_volume"].sum()
                bank_data_with_share = bank_data.copy()
                bank_data_with_share["market_share"] = bank_data["new_loan_volume"] / bank_data["round"].map(total_volume_by_round)
                bank_data_with_share["market_share"] = bank_data_with_share["market_share"].fillna(0)
                
                avg_market_share = bank_data_with_share["market_share"].mean()
                total_loans = bank_data["new_loan_count"].sum()
                avg_rate = bank_data["offered_rate"].mean()
                rounds_survived = len(bank_data)
                
                # Get final equity from last round of market data
                final_equity = bank_data.iloc[-1]["equity"]
                survived = not bank_data.iloc[-1]["bankrupt_flag"]
                final_market_share = bank_data_with_share.iloc[-1]["market_share"]
            else:
                avg_market_share = 0
                total_loans = 0
                avg_rate = 0
                rounds_survived = 0
                final_equity = 0
                survived = False
                final_market_share = 0

            outcome = BankOutcome(
                bank_name=initial_bank.id,
                initial_strategy=initial_bank.strategy.value,
                initial_equity=initial_bank.initial_equity,
                initial_image=initial_bank.image_score,
                initial_speed=initial_bank.execution_speed,
                final_equity=final_equity,
                final_market_share=final_market_share,
                avg_market_share=avg_market_share,
                survived=survived,
                rounds_survived=rounds_survived,
                total_loans_originated=int(total_loans),
                avg_interest_rate=avg_rate,
            )
            outcomes.append(outcome)

        return outcomes

    def _summarize_market_conditions(self, state: SimulationState) -> Dict:
        """Summarize key market conditions from the simulation."""
        market_log_df = pd.DataFrame(state["market_log"])

        # Calculate market-wide metrics
        final_round = market_log_df["round"].max()
        final_round_data = market_log_df[market_log_df["round"] == final_round]
        
        conditions = {
            "avg_rate": float(market_log_df["offered_rate"].mean() / 10000),  # Convert bps to decimal and to Python float
            "rate_variance": float(market_log_df["offered_rate"].std() / 10000),  # Convert bps to decimal and to Python float
            "final_concentration": float(self._calculate_hhi(final_round_data)),  # Convert to Python float
            "bankruptcy_count": int(final_round_data["bankrupt_flag"].sum()),  # Count TRUE values and convert to Python int
            "avg_consumer_sensitivity": float(state["consumers"]["rate_sensitivity"].mean()) if "consumers" in state else 0.5,
            "dominant_strategy": str(self._get_dominant_strategy_from_market_log(final_round_data)),  # Ensure it's a Python string
        }

        return conditions

    def _calculate_hhi(self, round_data: pd.DataFrame) -> float:
        """Calculate Herfindahl-Hirschman Index for market concentration."""
        if round_data.empty:
            return 0
            
        # Calculate market shares for the final round
        total_volume = round_data["new_loan_volume"].sum()
        if total_volume == 0:
            return 0
            
        market_shares = round_data["new_loan_volume"] / total_volume
        
        # HHI = sum of squared market shares * 10000
        return (market_shares**2).sum() * 10000

    def _get_dominant_strategy_from_market_log(self, final_round_data: pd.DataFrame) -> str:
        """Determine which strategy dominates among surviving banks."""
        # Filter surviving banks (not bankrupt)
        surviving = final_round_data[final_round_data["bankrupt_flag"] == False]
        if surviving.empty:
            return "None"

        # Group by strategy and sum equity
        strategy_equity = surviving.groupby("strategy")["equity"].sum()
        
        if strategy_equity.empty:
            return "None"
            
        # Return strategy with highest total equity
        return strategy_equity.idxmax()

    def _get_similar_market_lessons(self, state: SimulationState) -> List[Dict]:
        """Get lessons from historically similar market conditions."""
        market_conditions = self._summarize_market_conditions(state)
        return self.memory_store.get_similar_market_lessons(market_conditions)

    async def _generate_lessons(
        self,
        summary_content: str,
        bank_outcomes: List[BankOutcome],
        market_conditions: Dict,
        historical_patterns: List[Dict],
        similar_lessons: List[Dict],
    ) -> List[Lesson]:
        """Use AI to generate lessons from simulation results."""

        # Prepare context for AI
        outcomes_summary = self._format_outcomes_for_ai(bank_outcomes)
        historical_context = self._format_historical_patterns(historical_patterns)

        prompt = f"""Analyze this loan market simulation and extract key lessons learned.

SIMULATION SUMMARY:
{summary_content}

BANK OUTCOMES:
{outcomes_summary}

MARKET CONDITIONS:
- Average interest rate: {market_conditions['avg_rate']:.1%}
- Rate variance: {market_conditions['rate_variance']:.3%}
- Final market concentration (HHI): {market_conditions['final_concentration']:.0f}
- Number of bankruptcies: {market_conditions['bankruptcy_count']}
- Dominant strategy: {market_conditions['dominant_strategy']}

HISTORICAL PATTERNS FROM PREVIOUS SIMULATIONS:
{historical_context}

Please extract 3-5 specific, actionable lessons from this simulation. Focus on:
1. What strategies worked and why
2. What strategies failed and why
3. Market dynamics and equilibrium patterns
4. Bankruptcy predictors and warning signs
5. Optimal bank characteristics for different strategies

Format each lesson as:
LESSON_TYPE: [strategy/market_condition/bankruptcy/equilibrium]
LESSON: [Clear, specific lesson text]
CONFIDENCE: [0.0-1.0 based on evidence strength]

Be specific about numbers, thresholds, and conditions."""

        messages = [
            SystemMessage(
                content="You are an expert financial analyst extracting lessons from market simulations."
            ),
            HumanMessage(content=prompt),
        ]

        response = await self.llm.ainvoke(messages)
        lessons = self._parse_lessons_response(response.content, market_conditions)

        return lessons

    def _format_outcomes_for_ai(self, outcomes: List[BankOutcome]) -> str:
        """Format bank outcomes for AI analysis."""
        lines = []

        # Sort by success (survival and final equity)
        sorted_outcomes = sorted(
            outcomes, key=lambda x: (x.survived, x.final_equity), reverse=True
        )

        for outcome in sorted_outcomes:
            status = "SURVIVED" if outcome.survived else "BANKRUPT"
            lines.append(
                f"{outcome.bank_name} ({outcome.initial_strategy}): "
                f"{status}, Initial Equity: ${outcome.initial_equity:.0f}M, "
                f"Final Equity: ${outcome.final_equity:.0f}M, "
                f"Avg Market Share: {outcome.avg_market_share:.1%}, "
                f"Image: {outcome.initial_image:.1f}, "
                f"Speed: {outcome.initial_speed:.1f}"
            )

        return "\n".join(lines)

    def _format_historical_patterns(self, patterns: List[Dict]) -> str:
        """Format historical patterns for context."""
        if not patterns:
            return "No significant historical patterns yet."

        lines = []
        for pattern in patterns[:5]:  # Top 5 patterns
            lines.append(
                f"- {pattern['pattern_description']} "
                f"(Success rate: {pattern['success_rate']:.1%}, "
                f"Observations: {pattern['observation_count']})"
            )

        return "\n".join(lines)

    def _parse_lessons_response(
        self, response: str, market_conditions: Dict
    ) -> List[Lesson]:
        """Parse AI response into Lesson objects."""
        lessons = []

        # Parse each lesson block
        lesson_pattern = (
            r"LESSON_TYPE:\s*(\w+)\s*\nLESSON:\s*(.+?)\s*\nCONFIDENCE:\s*([\d.]+)"
        )
        matches = re.finditer(lesson_pattern, response, re.MULTILINE | re.DOTALL)

        for match in matches:
            lesson_type = match.group(1).lower()
            lesson_text = match.group(2).strip()
            try:
                confidence = float(match.group(3))
            except:
                confidence = 0.7  # Default confidence

            lesson = Lesson(
                lesson_type=lesson_type,
                lesson_text=lesson_text,
                confidence=min(1.0, max(0.0, confidence)),
                conditions=market_conditions,
            )
            lessons.append(lesson)

        # Fallback if parsing fails
        if not lessons and response:
            lessons.append(
                Lesson(
                    lesson_type="general",
                    lesson_text=response[:500],  # First 500 chars
                    confidence=0.5,
                    conditions=market_conditions,
                )
            )

        return lessons

    def _extract_patterns(
        self, outcomes: List[BankOutcome], market_conditions: Dict
    ) -> List[StrategyPattern]:
        """Extract strategy patterns from outcomes."""
        patterns = []

        # Group by strategy
        strategy_groups = {}
        for outcome in outcomes:
            strategy = outcome.initial_strategy
            if strategy not in strategy_groups:
                strategy_groups[strategy] = []
            strategy_groups[strategy].append(outcome)

        # Analyze each strategy
        for strategy, banks in strategy_groups.items():
            survived = [b for b in banks if b.survived]
            success_rate = len(survived) / len(banks) if banks else 0

            # Extract patterns based on characteristics
            if success_rate > 0.7 and len(banks) >= 2:
                # Successful strategy pattern
                avg_equity = sum(b.initial_equity for b in survived) / len(survived)
                avg_image = sum(b.initial_image for b in survived) / len(survived)

                pattern = StrategyPattern(
                    pattern_description=f"{strategy} strategy with >${avg_equity:.0f}M equity and >{avg_image:.1f} image score",
                    success_rate=success_rate,
                    conditions=f"Market rate ~{market_conditions['avg_rate']:.1%}",
                    observation_count=len(banks),
                    example_banks=[b.bank_name for b in survived[:3]],
                )
                patterns.append(pattern)

            elif success_rate < 0.3 and len(banks) >= 2:
                # Failed strategy pattern
                avg_equity = sum(b.initial_equity for b in banks) / len(banks)

                pattern = StrategyPattern(
                    pattern_description=f"{strategy} strategy with <{avg_equity:.0f}M equity tends to fail",
                    success_rate=1 - success_rate,  # Failure rate as success of pattern
                    conditions=f"High competition environment",
                    observation_count=len(banks),
                    example_banks=[b.bank_name for b in banks if not b.survived][:3],
                )
                patterns.append(pattern)

        return patterns

    def _generate_lessons_markdown(
        self,
        lessons: List[Lesson],
        patterns: List[StrategyPattern],
        outcomes: List[BankOutcome],
        market_conditions: Dict,
    ) -> str:
        """Generate markdown file with lessons learned."""

        lines = [
            "# Lessons Learned",
            f"\n## Market Conditions",
            f"- Average Market Rate: {market_conditions['avg_rate']:.2%}",
            f"- Rate Volatility: {market_conditions['rate_variance']:.3%}",
            f"- Market Concentration (HHI): {market_conditions['final_concentration']:.0f}",
            f"- Bankruptcies: {market_conditions['bankruptcy_count']}",
            f"- Dominant Strategy: {market_conditions['dominant_strategy']}",
            f"\n## Key Lessons",
        ]

        # Group lessons by type
        by_type = {}
        for lesson in lessons:
            if lesson.lesson_type not in by_type:
                by_type[lesson.lesson_type] = []
            by_type[lesson.lesson_type].append(lesson)

        for lesson_type, type_lessons in by_type.items():
            lines.append(f"\n### {lesson_type.title()} Insights")
            for lesson in type_lessons:
                confidence_pct = int(lesson.confidence * 100)
                lines.append(
                    f"- **[{confidence_pct}% confidence]** {lesson.lesson_text}"
                )

        # Add strategy patterns
        lines.append(f"\n## Strategy Patterns")
        for pattern in patterns:
            lines.append(
                f"- {pattern.pattern_description} "
                f"(Success: {pattern.success_rate:.0%}, n={pattern.observation_count})"
            )

        # Add performance summary
        lines.append(f"\n## Bank Performance Summary")
        lines.append(
            "| Bank | Strategy | Initial Equity | Final Equity | Status | Avg Market Share |"
        )
        lines.append(
            "|------|----------|----------------|--------------|--------|------------------|"
        )

        sorted_outcomes = sorted(outcomes, key=lambda x: x.final_equity, reverse=True)
        for outcome in sorted_outcomes:
            status = "✓ Survived" if outcome.survived else "✗ Bankrupt"
            lines.append(
                f"| {outcome.bank_name} | {outcome.initial_strategy} | "
                f"${outcome.initial_equity:.0f}M | ${outcome.final_equity:.0f}M | "
                f"{status} | {outcome.avg_market_share:.1%} |"
            )

        # Historical context
        historical_patterns = self.memory_store.get_strategy_patterns(
            min_observations=10
        )
        if historical_patterns:
            lines.append(f"\n## Historical Context")
            lines.append("Based on all previous simulations:")
            for pattern in historical_patterns[:5]:
                lines.append(
                    f"- {pattern['pattern_description']} "
                    f"({pattern['success_rate']:.0%} success, "
                    f"{pattern['observation_count']} observations)"
                )

        return "\n".join(lines)
