"""
AI agent for synthesizing final lessons across all megaruns.
"""

import re
import json
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.memory_store import MemoryStore

logger = logging.getLogger(__name__)


@dataclass
class SynthesisInsight:
    """A cross-megarun insight from synthesis analysis."""

    insight_type: str  # principle, pattern, recommendation, warning
    insight_text: str
    confidence: float
    supporting_evidence: List[str]
    megaruns_involved: List[int]


class SynthesisAgent:
    """Agent that synthesizes final insights across all megaruns."""

    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.3):
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        self.memory_store = MemoryStore()

    async def synthesize_final_lessons(
        self,
        megarun_results: List[Dict],
        megarun_lessons: List[str],
        hypothesis_results: List[Dict],
    ) -> Tuple[List[SynthesisInsight], str]:
        """Synthesize final lessons across all completed megaruns."""

        # Analyze cross-megarun patterns
        patterns = self._identify_cross_megarun_patterns(megarun_results)

        # Generate synthesis insights
        insights = await self._generate_synthesis_insights(
            megarun_results, megarun_lessons, hypothesis_results, patterns
        )

        # Generate final report
        final_report = self._generate_final_report(
            insights, megarun_results, hypothesis_results, patterns
        )

        return insights, final_report

    def _identify_cross_megarun_patterns(self, megarun_results: List[Dict]) -> Dict:
        """Identify patterns across megaruns."""
        if len(megarun_results) < 2:
            return {}

        patterns = {}

        # Configuration-outcome correlations
        configs = []
        outcomes = []

        for result in megarun_results:
            config = result.get("market_configuration", {})
            outcome = result.get("market_outcomes", {})

            configs.append(config)
            outcomes.append(outcome)

        # Simple pattern detection
        patterns["equity_stability_correlation"] = (
            self._analyze_equity_stability_pattern(configs, outcomes)
        )
        patterns["strategy_concentration_pattern"] = (
            self._analyze_strategy_concentration_pattern(configs, outcomes)
        )
        patterns["image_competition_pattern"] = self._analyze_image_competition_pattern(
            configs, outcomes
        )
        patterns["hypothesis_validation_summary"] = (
            self._summarize_hypothesis_validations(megarun_results)
        )

        return patterns

    def _analyze_equity_stability_pattern(
        self, configs: List[Dict], outcomes: List[Dict]
    ) -> Dict:
        """Analyze relationship between equity levels and market stability."""
        equity_levels = [config.get("avg_equity", 0) for config in configs]
        survival_rates = [outcome.get("survival_rate", 0) for outcome in outcomes]
        bankruptcies = [outcome.get("total_bankruptcies", 0) for outcome in outcomes]

        if len(equity_levels) < 2:
            return {"correlation": "insufficient_data"}

        # Simple correlation analysis
        equity_stability_pairs = list(zip(equity_levels, survival_rates))
        equity_bankruptcy_pairs = list(zip(equity_levels, bankruptcies))

        return {
            "equity_survival_pairs": equity_stability_pairs,
            "equity_bankruptcy_pairs": equity_bankruptcy_pairs,
            "pattern": (
                "higher_equity_more_stable"
                if len(equity_stability_pairs) > 1
                and equity_stability_pairs[-1][1] > equity_stability_pairs[0][1]
                and equity_stability_pairs[-1][0] > equity_stability_pairs[0][0]
                else "mixed"
            ),
        }

    def _analyze_strategy_concentration_pattern(
        self, configs: List[Dict], outcomes: List[Dict]
    ) -> Dict:
        """Analyze relationship between strategy mix and market concentration."""
        grow_pcts = [config.get("grow_strategy_pct", 0) for config in configs]
        concentrations = [
            outcome.get("final_market_concentration_hhi", 0) for outcome in outcomes
        ]

        return {
            "strategy_concentration_pairs": list(zip(grow_pcts, concentrations)),
            "pattern": (
                "more_growth_more_concentration"
                if len(grow_pcts) > 1
                and any(g > 0.6 for g in grow_pcts)
                and max(concentrations) > min(concentrations) * 1.5
                else "stable"
            ),
        }

    def _analyze_image_competition_pattern(
        self, configs: List[Dict], outcomes: List[Dict]
    ) -> Dict:
        """Analyze relationship between image differentiation and competition."""
        image_scores = [config.get("avg_image_score", 0) for config in configs]
        rate_volatilities = [outcome.get("rate_volatility", 0) for outcome in outcomes]

        return {
            "image_volatility_pairs": list(zip(image_scores, rate_volatilities)),
            "pattern": "analyzed",
        }

    def _summarize_hypothesis_validations(self, megarun_results: List[Dict]) -> Dict:
        """Summarize hypothesis validation results."""
        validations = {}
        for i, result in enumerate(megarun_results, 1):
            hypothesis_result = result.get("hypothesis_result")
            if hypothesis_result:
                validations[f"megarun_{i}"] = {
                    "hypothesis": hypothesis_result.get("hypothesis", ""),
                    "result": hypothesis_result.get("result", ""),
                    "confidence": hypothesis_result.get("confidence", 0),
                }
        return validations

    async def _generate_synthesis_insights(
        self,
        megarun_results: List[Dict],
        megarun_lessons: List[str],
        hypothesis_results: List[Dict],
        patterns: Dict,
    ) -> List[SynthesisInsight]:
        """Generate synthesis insights using AI."""

        # Format all inputs for AI
        results_summary = self._format_megarun_results(megarun_results)
        lessons_summary = self._format_megarun_lessons(megarun_lessons)
        hypotheses_summary = self._format_hypothesis_results(hypothesis_results)
        patterns_summary = self._format_patterns(patterns)

        prompt = f"""Analyze all megarun results and synthesize final insights about optimal market design.

MEGARUN RESULTS SUMMARY:
{results_summary}

INDIVIDUAL MEGARUN LESSONS:
{lessons_summary}

HYPOTHESIS TEST RESULTS:
{hypotheses_summary}

CROSS-MEGARUN PATTERNS:
{patterns_summary}

Synthesize 5-7 HIGH-LEVEL insights that:
1. Combine learnings across all megaruns
2. Identify optimal market design principles
3. Provide actionable recommendations
4. Highlight validated theories vs failed hypotheses
5. Suggest areas for future investigation

Focus on:
- What market configurations work best and why
- Universal principles vs context-dependent factors  
- Trade-offs between stability, efficiency, and competition
- Warning signs of market instability
- Recommendations for market designers

Format each insight as:
INSIGHT_TYPE: [principle/pattern/recommendation/warning]
INSIGHT: [Clear, actionable insight]
CONFIDENCE: [0.0-1.0 based on evidence strength]
EVIDENCE: [Which megaruns support this, specific data points]

Prioritize insights with strong evidence from multiple megaruns."""

        messages = [
            SystemMessage(
                content="You are a senior market design expert synthesizing insights from extensive empirical research."
            ),
            HumanMessage(content=prompt),
        ]

        response = await self.llm.ainvoke(messages)
        insights = self._parse_synthesis_response(response.content, megarun_results)

        return insights

    def _format_megarun_results(self, results: List[Dict]) -> str:
        """Format megarun results for synthesis."""
        lines = []
        for i, result in enumerate(results, 1):
            config = result.get("market_configuration", {})
            outcome = result.get("market_outcomes", {})

            lines.append(f"Megarun {i}:")
            lines.append(
                f"  Config: {config.get('grow_strategy_pct', 0):.0%} Growth, "
                f"${config.get('avg_equity', 0):.0f}M avg equity, "
                f"{config.get('avg_image_score', 0):.2f} avg image"
            )
            lines.append(
                f"  Outcome: {outcome.get('survival_rate', 0):.0%} survival, "
                f"{outcome.get('total_bankruptcies', 0)} bankruptcies, "
                f"{outcome.get('final_market_concentration_hhi', 0):.0f} HHI"
            )
            lines.append("")

        return "\n".join(lines)

    def _format_megarun_lessons(self, lessons: List[str]) -> str:
        """Format individual megarun lessons."""
        formatted = []
        for i, lesson in enumerate(lessons, 1):
            formatted.append(f"Megarun {i} Lessons:")
            formatted.append(lesson[:500] + "..." if len(lesson) > 500 else lesson)
            formatted.append("")

        return "\n".join(formatted)

    def _format_hypothesis_results(self, results: List[Dict]) -> str:
        """Format hypothesis test results."""
        lines = []
        for i, result in enumerate(results, 1):
            if result:
                lines.append(f"Megarun {i}: {result.get('hypothesis', '')}")
                lines.append(
                    f"  Result: {result.get('result', '')} ({result.get('confidence', 0):.0%})"
                )
                lines.append(f"  Evidence: {result.get('evidence', '')[:200]}...")
                lines.append("")

        return "\n".join(lines)

    def _format_patterns(self, patterns: Dict) -> str:
        """Format cross-megarun patterns."""
        lines = []
        for pattern_name, pattern_data in patterns.items():
            lines.append(f"{pattern_name}: {json.dumps(pattern_data, indent=2)}")
            lines.append("")

        return "\n".join(lines)

    def _parse_synthesis_response(
        self, response: str, megarun_results: List[Dict]
    ) -> List[SynthesisInsight]:
        """Parse AI response into SynthesisInsight objects."""
        insights = []

        # Parse each insight block
        insight_pattern = r"INSIGHT_TYPE:\s*(\w+)\s*\nINSIGHT:\s*(.+?)\s*\nCONFIDENCE:\s*([\d.]+)\s*\nEVIDENCE:\s*(.+?)(?=\n\n|\nINSIGHT_TYPE:|\Z)"
        matches = re.finditer(insight_pattern, response, re.MULTILINE | re.DOTALL)

        for match in matches:
            insight_type = match.group(1).lower()
            insight_text = match.group(2).strip()
            evidence_text = match.group(4).strip()

            try:
                confidence = float(match.group(3))
            except:
                confidence = 0.7

            # Extract megarun numbers from evidence
            megarun_numbers = []
            megarun_matches = re.findall(
                r"megarun\s+(\d+)", evidence_text, re.IGNORECASE
            )
            megarun_numbers = [int(m) for m in megarun_matches]

            insight = SynthesisInsight(
                insight_type=insight_type,
                insight_text=insight_text,
                confidence=min(1.0, max(0.0, confidence)),
                supporting_evidence=[evidence_text],
                megaruns_involved=megarun_numbers,
            )
            insights.append(insight)

        return insights

    def _generate_final_report(
        self,
        insights: List[SynthesisInsight],
        megarun_results: List[Dict],
        hypothesis_results: List[Dict],
        patterns: Dict,
    ) -> str:
        """Generate comprehensive final report."""

        lines = [
            "# Meta-Simulation Final Analysis",
            f"\n## Executive Summary",
            f"Completed {len(megarun_results)} megaruns testing different market configurations.",
            f"Validated {sum(1 for h in hypothesis_results if h and h.get('result') == 'CONFIRMED')} hypotheses, "
            f"rejected {sum(1 for h in hypothesis_results if h and h.get('result') == 'REJECTED')}, "
            f"with {sum(1 for h in hypothesis_results if h and h.get('result') == 'INCONCLUSIVE')} inconclusive.",
            f"\n## Key Insights",
        ]

        # Group insights by type
        by_type = {}
        for insight in insights:
            if insight.insight_type not in by_type:
                by_type[insight.insight_type] = []
            by_type[insight.insight_type].append(insight)

        for insight_type, type_insights in by_type.items():
            lines.append(f"\n### {insight_type.title()}s")
            for insight in type_insights:
                confidence_pct = int(insight.confidence * 100)
                megaruns_str = (
                    ", ".join(map(str, insight.megaruns_involved))
                    if insight.megaruns_involved
                    else "All"
                )
                lines.append(
                    f"- **[{confidence_pct}% confidence, Megaruns {megaruns_str}]** {insight.insight_text}"
                )

        # Add megarun summary
        lines.append(f"\n## Megarun Summary")
        for i, result in enumerate(megarun_results, 1):
            config = result.get("market_configuration", {})
            outcome = result.get("market_outcomes", {})
            hypothesis = result.get("hypothesis_result", {})

            lines.append(f"\n### Megarun {i}")
            lines.append(
                f"**Configuration**: {config.get('grow_strategy_pct', 0):.0%} Growth strategy, "
                f"${config.get('avg_equity', 0):,.0f}M average equity"
            )
            lines.append(
                f"**Results**: {outcome.get('survival_rate', 0):.0%} survival rate, "
                f"{outcome.get('total_bankruptcies', 0)} bankruptcies, "
                f"{outcome.get('final_market_concentration_hhi', 0):.0f} HHI"
            )

            if hypothesis:
                lines.append(f"**Hypothesis**: {hypothesis.get('hypothesis', '')}")
                lines.append(
                    f"**Result**: {hypothesis.get('result', '')} ({hypothesis.get('confidence', 0):.0%} confidence)"
                )

        # Add recommendations
        lines.append(f"\n## Recommendations for Market Designers")
        recommendations = [
            insight for insight in insights if insight.insight_type == "recommendation"
        ]
        if recommendations:
            for rec in recommendations:
                lines.append(f"- {rec.insight_text}")
        else:
            lines.append(
                "- Based on the analysis, focus on configurations that balance growth and stability"
            )
            lines.append("- Consider equity requirements as a key stability factor")
            lines.append(
                "- Monitor market concentration to prevent monopolistic outcomes"
            )

        # Add future research
        lines.append(f"\n## Future Research Directions")
        lines.append("- Test different consumer behavior parameters")
        lines.append("- Explore longer-term market evolution (>10 rounds)")
        lines.append("- Investigate regulatory intervention effects")
        lines.append("- Study network effects and bank partnerships")

        return "\n".join(lines)
