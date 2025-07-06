"""
AI agent for extracting macro-level lessons from megarun results.
"""

import re
import json
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import pandas as pd

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.memory_store import MemoryStore

logger = logging.getLogger(__name__)


@dataclass
class MegarunLesson:
    """A macro-level lesson learned from a megarun."""
    lesson_type: str  # market_configuration, hypothesis_validation, strategy_emergence, stability
    lesson_text: str
    confidence: float  # 0-1 based on evidence strength
    market_configuration: Dict  # Market setup that generated this lesson
    

@dataclass 
class HypothesisResult:
    """Result of testing a hypothesis in a megarun."""
    hypothesis: str
    result: str  # confirmed, rejected, inconclusive
    confidence: float
    evidence: str


class MegarunLessonsAgent:
    """Agent that extracts macro-level lessons from completed megaruns."""
    
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.3):
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        self.memory_store = MemoryStore()
        
    async def extract_megarun_lessons(self, 
                                    megarun_number: int,
                                    subgraph_results: Dict,
                                    bank_configuration: Dict,
                                    hypothesis: Optional[Dict] = None,
                                    historical_lessons: List[Dict] = None) -> Tuple[List[MegarunLesson], HypothesisResult, str]:
        """Extract macro-level lessons from a completed megarun."""
        
        # Analyze market configuration
        market_config = self._analyze_market_configuration(bank_configuration)
        
        # Get market outcomes from subgraph state
        market_outcomes = self._extract_market_outcomes({
            "market_log": subgraph_results.get("market_log", [])
        })
        
        # Get historical context
        if not historical_lessons:
            historical_lessons = self.memory_store.get_historical_megarun_patterns()
            
        # Generate lessons using AI
        lessons = await self._generate_macro_lessons(
            megarun_number,
            market_config,
            market_outcomes,
            subgraph_results.get('lessons_content', ''),
            historical_lessons
        )
        
        # Test hypothesis if provided
        hypothesis_result = await self._test_hypothesis(
            hypothesis, market_outcomes, market_config
        ) if hypothesis else None
        
        # Generate megarun report
        report = self._generate_megarun_report(
            megarun_number, lessons, hypothesis_result, market_config, market_outcomes
        )
        
        return lessons, hypothesis_result, report
        
    def _analyze_market_configuration(self, bank_configuration: Dict) -> Dict:
        """Analyze the market configuration characteristics."""
        banks = bank_configuration.get('bank_params', {}).get('individual_banks', {})
        
        if not banks:
            return {}
            
        # Calculate configuration metrics
        total_equity = sum(bank.get('equity_start', 0) for bank in banks.values())
        avg_equity = total_equity / len(banks)
        
        strategies = [bank.get('strategy', '') for bank in banks.values()]
        grow_count = sum(1 for s in strategies if s == 'Grow')
        maintain_count = sum(1 for s in strategies if s == 'Maintain')
        
        image_scores = [bank.get('image_score', 0) for bank in banks.values()]
        avg_image = sum(image_scores) / len(image_scores) if image_scores else 0
        
        execution_speeds = [bank.get('execution_speed', 0) for bank in banks.values()]
        avg_speed = sum(execution_speeds) / len(execution_speeds) if execution_speeds else 0
        
        return {
            'total_banks': len(banks),
            'total_equity': float(total_equity),
            'avg_equity': float(avg_equity),
            'equity_concentration': float(max(bank.get('equity_start', 0) for bank in banks.values()) / total_equity),
            'grow_strategy_pct': float(grow_count / len(banks)),
            'maintain_strategy_pct': float(maintain_count / len(banks)),
            'avg_image_score': float(avg_image),
            'avg_execution_speed': float(avg_speed),
            'strategy_distribution': {'Grow': grow_count, 'Maintain': maintain_count}
        }
        
    def _extract_market_outcomes(self, subgraph_results: Dict) -> Dict:
        """Extract key market outcomes from subgraph results."""
        market_log = subgraph_results.get('market_log', [])
        if not market_log:
            return {}
            
        market_df = pd.DataFrame(market_log)
        
        # Calculate market-level metrics
        final_round = market_df['round'].max()
        final_round_data = market_df[market_df['round'] == final_round]
        
        total_final_equity = final_round_data['equity'].sum()
        bankruptcies = final_round_data['bankrupt_flag'].sum()
        
        # Market concentration (HHI)
        if not final_round_data.empty:
            total_volume = final_round_data['new_loan_volume'].sum()
            if total_volume > 0:
                market_shares = final_round_data['new_loan_volume'] / total_volume
                hhi = (market_shares**2).sum() * 10000
            else:
                hhi = 0
        else:
            hhi = 0
            
        # Rate dynamics
        avg_rate = market_df['offered_rate'].mean()
        rate_volatility = market_df.groupby('round')['offered_rate'].std().mean()
        
        return {
            'survival_rate': float((len(final_round_data) - bankruptcies) / len(final_round_data)) if len(final_round_data) > 0 else 0,
            'total_bankruptcies': int(bankruptcies),
            'final_market_concentration_hhi': float(hhi),
            'avg_interest_rate': float(avg_rate / 10000),  # Convert from bps
            'rate_volatility': float(rate_volatility / 10000) if pd.notna(rate_volatility) else 0,
            'total_final_equity': float(total_final_equity),
            'rounds_completed': int(final_round),
            'market_efficiency': float(1 - (bankruptcies / len(final_round_data))) if len(final_round_data) > 0 else 0
        }
        
    async def _generate_macro_lessons(self,
                                    megarun_number: int,
                                    market_config: Dict,
                                    market_outcomes: Dict,
                                    subgraph_lessons: str,
                                    historical_lessons: List[Dict]) -> List[MegarunLesson]:
        """Use AI to generate macro-level lessons."""
        
        # Format historical context
        historical_context = self._format_historical_context(historical_lessons)
        
        prompt = f"""Analyze this megarun (#{megarun_number}) and extract macro-level lessons about market design and configuration.

MARKET CONFIGURATION:
- Total Banks: {market_config.get('total_banks', 0)}
- Average Equity: ${market_config.get('avg_equity', 0):,.0f}M
- Strategy Mix: {market_config.get('grow_strategy_pct', 0):.1%} Growth, {market_config.get('maintain_strategy_pct', 0):.1%} Maintain
- Average Image Score: {market_config.get('avg_image_score', 0):.2f}
- Equity Concentration: {market_config.get('equity_concentration', 0):.1%} (largest bank share)

MARKET OUTCOMES:
- Survival Rate: {market_outcomes.get('survival_rate', 0):.1%}
- Bankruptcies: {market_outcomes.get('total_bankruptcies', 0)}
- Market Concentration (HHI): {market_outcomes.get('final_market_concentration_hhi', 0):.0f}
- Average Rate: {market_outcomes.get('avg_interest_rate', 0):.2%}
- Rate Volatility: {market_outcomes.get('rate_volatility', 0):.3%}
- Market Efficiency: {market_outcomes.get('market_efficiency', 0):.1%}

MICRO-LESSONS FROM SUBGRAPH:
{subgraph_lessons[:1000]}...

HISTORICAL MACRO PATTERNS:
{historical_context}

Extract 3-5 MACRO-LEVEL lessons about:
1. How market configuration affects outcomes
2. Optimal market design principles
3. Configuration-outcome relationships
4. Market stability factors

Format each lesson as:
LESSON_TYPE: [market_configuration/stability/efficiency/competition]
LESSON: [Clear, specific lesson about market design]
CONFIDENCE: [0.0-1.0 based on evidence strength]

Focus on insights about market design, not individual bank strategies."""

        messages = [
            SystemMessage(content="You are an expert market design analyst extracting macro-level insights about market configuration and outcomes."),
            HumanMessage(content=prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        lessons = self._parse_macro_lessons_response(response.content, market_config)
        
        return lessons
        
    async def _test_hypothesis(self, hypothesis: Dict, market_outcomes: Dict, 
                             market_config: Dict) -> HypothesisResult:
        """Test a specific hypothesis against market results."""
        if not hypothesis:
            return None
            
        prompt = f"""Test this hypothesis against the market results:

HYPOTHESIS: {hypothesis.get('hypothesis', '')}
EXPECTED OUTCOME: {hypothesis.get('expected_outcome', '')}

ACTUAL MARKET CONFIGURATION:
{json.dumps(market_config, indent=2)}

ACTUAL MARKET OUTCOMES:
{json.dumps(market_outcomes, indent=2)}

Based on the evidence, is the hypothesis:
1. CONFIRMED: Strong evidence supports the hypothesis
2. REJECTED: Strong evidence contradicts the hypothesis  
3. INCONCLUSIVE: Mixed or insufficient evidence

Provide:
RESULT: [CONFIRMED/REJECTED/INCONCLUSIVE]
CONFIDENCE: [0.0-1.0]
EVIDENCE: [Specific evidence from the results]"""

        messages = [
            SystemMessage(content="You are a rigorous market researcher testing hypotheses against empirical evidence."),
            HumanMessage(content=prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        return self._parse_hypothesis_result(response.content, hypothesis)
        
    def _format_historical_context(self, historical_lessons: List[Dict]) -> str:
        """Format historical lessons for context."""
        if not historical_lessons:
            return "No historical patterns available yet."
            
        lines = []
        for lesson in historical_lessons[:5]:  # Top 5 patterns
            lines.append(
                f"- {lesson.get('lesson_text', '')} "
                f"(Confidence: {lesson.get('avg_confidence', 0):.1f}, "
                f"Observations: {lesson.get('observation_count', 0)})"
            )
            
        return "\n".join(lines)
        
    def _parse_macro_lessons_response(self, response: str, market_config: Dict) -> List[MegarunLesson]:
        """Parse AI response into MegarunLesson objects."""
        lessons = []
        
        # Parse each lesson block
        lesson_pattern = r"LESSON_TYPE:\s*(\w+)\s*\nLESSON:\s*(.+?)\s*\nCONFIDENCE:\s*([\d.]+)"
        matches = re.finditer(lesson_pattern, response, re.MULTILINE | re.DOTALL)
        
        for match in matches:
            lesson_type = match.group(1).lower()
            lesson_text = match.group(2).strip()
            try:
                confidence = float(match.group(3))
            except:
                confidence = 0.7  # Default confidence
                
            lesson = MegarunLesson(
                lesson_type=lesson_type,
                lesson_text=lesson_text,
                confidence=min(1.0, max(0.0, confidence)),
                market_configuration=market_config
            )
            lessons.append(lesson)
            
        # Fallback if parsing fails
        if not lessons and response:
            lessons.append(MegarunLesson(
                lesson_type="general",
                lesson_text=response[:500],  # First 500 chars
                confidence=0.5,
                market_configuration=market_config
            ))
            
        return lessons
        
    def _parse_hypothesis_result(self, response: str, hypothesis: Dict) -> HypothesisResult:
        """Parse hypothesis test result."""
        result_match = re.search(r"RESULT:\s*(CONFIRMED|REJECTED|INCONCLUSIVE)", response, re.IGNORECASE)
        confidence_match = re.search(r"CONFIDENCE:\s*([\d.]+)", response)
        evidence_match = re.search(r"EVIDENCE:\s*(.+?)(?:\n\n|\n[A-Z]+:|\Z)", response, re.DOTALL)
        
        result = result_match.group(1).upper() if result_match else "INCONCLUSIVE"
        confidence = float(confidence_match.group(1)) if confidence_match else 0.5
        evidence = evidence_match.group(1).strip() if evidence_match else response[:200]
        
        return HypothesisResult(
            hypothesis=hypothesis.get('hypothesis', ''),
            result=result,
            confidence=min(1.0, max(0.0, confidence)),
            evidence=evidence
        )
        
    def _generate_megarun_report(self, megarun_number: int, lessons: List[MegarunLesson],
                               hypothesis_result: Optional[HypothesisResult],
                               market_config: Dict, market_outcomes: Dict) -> str:
        """Generate comprehensive megarun report."""
        
        lines = [
            f"# Megarun #{megarun_number} Analysis Report",
            f"\n## Market Configuration",
            f"- **Banks**: {market_config.get('total_banks', 0)} total",
            f"- **Average Equity**: ${market_config.get('avg_equity', 0):,.0f}M",
            f"- **Strategy Mix**: {market_config.get('grow_strategy_pct', 0):.1%} Growth, {market_config.get('maintain_strategy_pct', 0):.1%} Maintain",
            f"- **Equity Concentration**: {market_config.get('equity_concentration', 0):.1%} (largest bank)",
            f"- **Average Image Score**: {market_config.get('avg_image_score', 0):.2f}",
            
            f"\n## Market Outcomes",
            f"- **Survival Rate**: {market_outcomes.get('survival_rate', 0):.1%}",
            f"- **Bankruptcies**: {market_outcomes.get('total_bankruptcies', 0)}",
            f"- **Market Concentration**: {market_outcomes.get('final_market_concentration_hhi', 0):.0f} HHI",
            f"- **Average Rate**: {market_outcomes.get('avg_interest_rate', 0):.2%}",
            f"- **Rate Volatility**: {market_outcomes.get('rate_volatility', 0):.3%}",
            f"- **Market Efficiency**: {market_outcomes.get('market_efficiency', 0):.1%}",
            
            f"\n## Macro-Level Lessons"
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
                lines.append(f"- **[{confidence_pct}% confidence]** {lesson.lesson_text}")
                
        # Add hypothesis results
        if hypothesis_result:
            lines.append(f"\n## Hypothesis Testing")
            lines.append(f"**Hypothesis**: {hypothesis_result.hypothesis}")
            lines.append(f"**Result**: {hypothesis_result.result} ({hypothesis_result.confidence:.0%} confidence)")
            lines.append(f"**Evidence**: {hypothesis_result.evidence}")
            
        return "\n".join(lines)