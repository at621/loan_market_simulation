"""
AI agent for preparing adaptive bank configurations based on lessons learned and hypotheses.
"""

import re
import json
import yaml
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.memory_store import MemoryStore

logger = logging.getLogger(__name__)


@dataclass
class ConfigurationHypothesis:
    """A hypothesis to test in the next megarun."""
    hypothesis: str
    expected_outcome: str
    rationale: str
    configuration_changes: Dict
    confidence: float


class BankConfigurationAgent:
    """Agent that prepares adaptive bank configurations for testing hypotheses."""
    
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.3):
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        self.memory_store = MemoryStore()
        
    async def prepare_bank_configuration(self, 
                                       megarun_number: int,
                                       base_config: Dict,
                                       historical_megarun_lessons: List[Dict],
                                       previous_hypothesis_results: List[Dict] = None) -> Tuple[Dict, ConfigurationHypothesis]:
        """Prepare bank configuration for the next megarun based on lessons and hypotheses."""
        
        if megarun_number == 1:
            # First megarun uses baseline configuration
            return base_config, ConfigurationHypothesis(
                hypothesis="Baseline configuration provides reference point",
                expected_outcome="Establishes baseline market dynamics",
                rationale="Need baseline to compare future configurations against",
                configuration_changes={},
                confidence=1.0
            )
            
        # For subsequent megaruns, generate hypothesis and modify configuration
        hypothesis = await self._generate_hypothesis(
            megarun_number, historical_megarun_lessons, previous_hypothesis_results
        )
        
        modified_config = await self._modify_bank_configuration(
            base_config, hypothesis, historical_megarun_lessons
        )
        
        return modified_config, hypothesis
        
    async def _generate_hypothesis(self, 
                                 megarun_number: int,
                                 historical_lessons: List[Dict],
                                 previous_results: List[Dict] = None) -> ConfigurationHypothesis:
        """Generate a hypothesis to test based on historical lessons."""
        
        # Format historical context
        lessons_summary = self._format_lessons_for_hypothesis(historical_lessons)
        previous_summary = self._format_previous_results(previous_results)
        
        prompt = f"""Based on historical market lessons, generate a specific hypothesis to test in megarun #{megarun_number}.

HISTORICAL MACRO LESSONS:
{lessons_summary}

PREVIOUS HYPOTHESIS RESULTS:
{previous_summary}

Generate a NEW hypothesis that:
1. Tests a different aspect of market configuration
2. Has clear, measurable expected outcomes
3. Can be implemented through bank parameter changes
4. Builds on previous findings

Focus on these testable areas:
- Market concentration effects (equity distribution)
- Strategy mix optimization (Growth vs Maintain ratios)
- Image/brand positioning effects
- Execution speed advantages
- Market stability factors

Format as:
HYPOTHESIS: [Clear, testable hypothesis]
EXPECTED_OUTCOME: [Specific measurable predictions]
RATIONALE: [Why this hypothesis is worth testing]
CONFIDENCE: [0.0-1.0 how confident you are this will show meaningful results]

Be specific about numbers and thresholds."""

        messages = [
            SystemMessage(content="You are a market design researcher generating testable hypotheses about optimal market configurations."),
            HumanMessage(content=prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        return self._parse_hypothesis_response(response.content)
        
    async def _modify_bank_configuration(self, 
                                       base_config: Dict,
                                       hypothesis: ConfigurationHypothesis,
                                       historical_lessons: List[Dict]) -> Dict:
        """Modify bank configuration to test the hypothesis."""
        
        # Get current bank configuration
        current_banks = base_config.get('bank_params', {}).get('individual_banks', {})
        
        # Format current configuration for AI
        banks_summary = self._format_banks_for_modification(current_banks)
        
        prompt = f"""Modify the bank configuration to test this hypothesis:

HYPOTHESIS: {hypothesis.hypothesis}
EXPECTED OUTCOME: {hypothesis.expected_outcome}
RATIONALE: {hypothesis.rationale}

CURRENT BANK CONFIGURATION:
{banks_summary}

Modify the bank parameters to create a market configuration that will test this hypothesis. 
You can adjust:
- equity_start (bank size)
- strategy (Grow/Maintain)
- image_score (0.0-1.0)
- execution_speed (0.0-1.0) 
- cost_of_funds_bps
- operating_cost_per_loan

Provide specific changes as:
BANK_ID: parameter=new_value, parameter=new_value
BANK_ID: parameter=new_value

For example:
B00: equity_start=75000000, image_score=0.95
B01: strategy=Maintain, equity_start=25000000

Be strategic - make changes that will clearly test your hypothesis while maintaining realistic market conditions."""

        messages = [
            SystemMessage(content="You are a market configuration designer implementing hypothesis tests through bank parameter modifications."),
            HumanMessage(content=prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Parse and apply modifications
        modified_config = self._apply_bank_modifications(base_config, response.content, hypothesis)
        
        return modified_config
        
    def _format_lessons_for_hypothesis(self, lessons: List[Dict]) -> str:
        """Format historical lessons for hypothesis generation."""
        if not lessons:
            return "No historical lessons available yet."
            
        lines = []
        for lesson in lessons[:10]:  # Top 10 lessons
            lines.append(
                f"- {lesson.get('lesson_text', '')} "
                f"(Type: {lesson.get('lesson_type', '')}, "
                f"Confidence: {lesson.get('avg_confidence', 0):.1f})"
            )
            
        return "\n".join(lines)
        
    def _format_previous_results(self, results: List[Dict]) -> str:
        """Format previous hypothesis results."""
        if not results:
            return "No previous hypothesis tests completed."
            
        lines = []
        for i, result in enumerate(results, 1):
            lines.append(
                f"Megarun {i}: {result.get('hypothesis', '')} -> "
                f"{result.get('result', '')} ({result.get('confidence', 0):.0%} confidence)"
            )
            
        return "\n".join(lines)
        
    def _format_banks_for_modification(self, banks: Dict) -> str:
        """Format bank configuration for AI modification."""
        lines = []
        for bank_id, config in banks.items():
            lines.append(
                f"{bank_id}: strategy={config.get('strategy', '')}, "
                f"equity=${config.get('equity_start', 0):,}, "
                f"image={config.get('image_score', 0):.2f}, "
                f"speed={config.get('execution_speed', 0):.2f}"
            )
        return "\n".join(lines)
        
    def _parse_hypothesis_response(self, response: str) -> ConfigurationHypothesis:
        """Parse AI response into ConfigurationHypothesis."""
        hypothesis_match = re.search(r"HYPOTHESIS:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
        outcome_match = re.search(r"EXPECTED_OUTCOME:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
        rationale_match = re.search(r"RATIONALE:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)
        confidence_match = re.search(r"CONFIDENCE:\s*([\d.]+)", response, re.IGNORECASE)
        
        return ConfigurationHypothesis(
            hypothesis=hypothesis_match.group(1).strip() if hypothesis_match else "Test market configuration effects",
            expected_outcome=outcome_match.group(1).strip() if outcome_match else "Observe market behavior changes",
            rationale=rationale_match.group(1).strip() if rationale_match else "Based on historical patterns",
            configuration_changes={},  # Will be filled by modification step
            confidence=float(confidence_match.group(1)) if confidence_match else 0.7
        )
        
    def _apply_bank_modifications(self, base_config: Dict, modifications: str, 
                                hypothesis: ConfigurationHypothesis) -> Dict:
        """Apply bank modifications from AI response to configuration."""
        # Deep copy the configuration
        modified_config = json.loads(json.dumps(base_config))
        banks = modified_config.get('bank_params', {}).get('individual_banks', {})
        
        # Parse modification commands
        modification_pattern = r"(\w+):\s*(.+?)(?:\n|$)"
        modifications_applied = {}
        
        for match in re.finditer(modification_pattern, modifications):
            bank_id = match.group(1).strip()
            changes_str = match.group(2).strip()
            
            if bank_id not in banks:
                continue
                
            # Parse individual parameter changes
            param_pattern = r"(\w+)\s*=\s*([^,\n]+)"
            changes_applied = {}
            
            for param_match in re.finditer(param_pattern, changes_str):
                param = param_match.group(1).strip()
                value_str = param_match.group(2).strip()
                
                # Convert value to appropriate type
                try:
                    if param in ['equity_start', 'portfolio_balance_start', 'cost_of_funds_bps', 
                               'operating_cost_per_loan', 'portfolio_rate_start_bps']:
                        value = int(float(value_str.replace(',', '')))
                    elif param in ['image_score', 'execution_speed']:
                        value = float(value_str)
                    else:
                        value = value_str  # String values like strategy
                        
                    # Apply the change
                    banks[bank_id][param] = value
                    changes_applied[param] = value
                    
                except (ValueError, KeyError) as e:
                    logger.warning(f"Failed to apply modification {param}={value_str} to {bank_id}: {e}")
                    continue
                    
            if changes_applied:
                modifications_applied[bank_id] = changes_applied
                
        # Store the changes made in the hypothesis
        hypothesis.configuration_changes = modifications_applied
        
        logger.info(f"Applied modifications: {modifications_applied}")
        return modified_config
        
    def save_bank_configuration(self, config: Dict, filename: str = "config/initialise_banks.yaml"):
        """Save the modified bank configuration to file."""
        bank_params = config.get('bank_params', {})
        
        with open(filename, 'w') as f:
            yaml.dump({'bank_params': bank_params}, f, default_flow_style=False)
            
        logger.info(f"Saved bank configuration to {filename}")
        
    def generate_predefined_hypotheses(self) -> List[ConfigurationHypothesis]:
        """Generate a set of predefined hypotheses for testing."""
        return [
            ConfigurationHypothesis(
                hypothesis="Higher average equity (50% increase) leads to more stable market with fewer bankruptcies",
                expected_outcome="Bankruptcy rate <20%, lower rate volatility, more even market shares",
                rationale="Higher capitalization should provide buffer against losses and reduce systemic risk",
                configuration_changes={},
                confidence=0.8
            ),
            ConfigurationHypothesis(
                hypothesis="More growth-oriented banks (80% Growth strategy) creates winner-take-all dynamics",
                expected_outcome="Higher market concentration (HHI >5000), more bankruptcies, greater rate volatility",
                rationale="Aggressive competition should lead to market shakeout and concentration",
                configuration_changes={},
                confidence=0.7
            ),
            ConfigurationHypothesis(
                hypothesis="Balanced image scores (0.6-0.8 range) optimize market competition vs stability",
                expected_outcome="Moderate concentration, balanced survival rates, stable pricing",
                rationale="Extreme differentiation may create monopolistic dynamics while no differentiation leads to price wars",
                configuration_changes={},
                confidence=0.6
            )
        ]