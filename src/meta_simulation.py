"""
Meta-simulation implementation that orchestrates multiple subgraph simulations.
"""

import asyncio
import os
import yaml
import json
import logging
from typing import Dict, List, Optional, Any
from langgraph.graph import StateGraph, START, END
import tempfile
from pathlib import Path

from src.models import MetaSimulationState
from src.simulation import LoanMarketSimulation
from src.memory_store import MemoryStore
from agents.bank_config_agent import BankConfigurationAgent
from agents.megarun_lessons_agent import MegarunLessonsAgent
from agents.synthesis_agent import SynthesisAgent

logger = logging.getLogger(__name__)


class MetaLoanMarketSimulation:
    """Meta-simulation that runs multiple loan market simulations with adaptive configurations."""
    
    def __init__(self, config_path: str = "config/config.yaml", 
                 banks_config_path: str = "config/initialise_banks.yaml",
                 total_megaruns: int = 3):
        """Initialize meta-simulation."""
        # Load base configuration
        with open(config_path, "r") as f:
            self.base_config = yaml.safe_load(f)
            
        with open(banks_config_path, "r") as f:
            self.base_banks_config = yaml.safe_load(f)
            
        # Merge configurations
        self.full_base_config = {**self.base_config, **self.base_banks_config}
        
        self.total_megaruns = total_megaruns
        self.memory_store = MemoryStore()
        
        # Initialize AI agents
        ai_params = self.base_config.get("ai_agent_params", {})
        self.bank_config_agent = BankConfigurationAgent(
            model_name=ai_params.get("model", "gpt-4o"),
            temperature=ai_params.get("temperature", 0.3)
        )
        self.megarun_lessons_agent = MegarunLessonsAgent(
            model_name=ai_params.get("model", "gpt-4o"),
            temperature=ai_params.get("temperature", 0.3)
        )
        self.synthesis_agent = SynthesisAgent(
            model_name=ai_params.get("model", "gpt-4o"),
            temperature=ai_params.get("temperature", 0.3)
        )
        
        # Create compiled subgraph
        self.subgraph = self._create_subgraph()
        
        # Build main graph
        self.graph = self._build_meta_graph()
        
    def _create_subgraph(self):
        """Create a compiled subgraph from the existing simulation."""
        # Create a temporary simulation instance to get its compiled graph
        temp_sim = LoanMarketSimulation("config/config.yaml", "config/initialise_banks.yaml")
        return temp_sim.graph
        
    def _build_meta_graph(self) -> StateGraph:
        """Build the meta-simulation graph."""
        builder = StateGraph(MetaSimulationState)
        
        # Add nodes
        builder.add_node("initialize_meta", self.initialize_meta_simulation)
        builder.add_node("prepare_bank_config", self.prepare_bank_configuration)
        builder.add_node("run_subgraph", self.run_subgraph_simulation)
        builder.add_node("extract_megarun_lessons", self.extract_megarun_lessons)
        builder.add_node("synthesize_final_lessons", self.synthesize_final_lessons)
        
        # Add edges
        builder.add_edge(START, "initialize_meta")
        builder.add_edge("initialize_meta", "prepare_bank_config")
        builder.add_edge("prepare_bank_config", "run_subgraph")
        builder.add_edge("run_subgraph", "extract_megarun_lessons")
        
        # Loop or end condition
        builder.add_conditional_edges(
            "extract_megarun_lessons",
            self.check_meta_continuation,
            {"continue": "prepare_bank_config", "end": "synthesize_final_lessons"}
        )
        
        builder.add_edge("synthesize_final_lessons", END)
        
        return builder.compile()
        
    def initialize_meta_simulation(self, state: MetaSimulationState) -> MetaSimulationState:
        """Initialize the meta-simulation."""
        logger.info("Initializing meta-simulation...")
        
        # Store meta-simulation in database
        meta_sim_id = self.memory_store.store_meta_simulation(
            self.total_megaruns, self.full_base_config
        )
        
        return {
            "current_megarun": 1,
            "total_megaruns": self.total_megaruns,
            "base_config": self.full_base_config,
            "current_bank_config": {},
            "megarun_results": [],
            "megarun_lessons": [],
            "final_synthesis": None,
            "tested_hypotheses": [],
            "hypothesis_results": [],
            "meta_simulation_id": meta_sim_id
        }
        
    async def prepare_bank_configuration(self, state: MetaSimulationState) -> MetaSimulationState:
        """Prepare bank configuration for the current megarun."""
        current_megarun = state["current_megarun"]
        logger.info(f"Preparing configuration for megarun {current_megarun}...")
        
        # Get historical lessons for context
        historical_lessons = self.memory_store.get_historical_megarun_patterns()
        
        # Prepare configuration and hypothesis
        bank_config, hypothesis = await self.bank_config_agent.prepare_bank_configuration(
            current_megarun,
            state["base_config"],
            historical_lessons,
            state["hypothesis_results"]
        )
        
        # Save the modified bank configuration to a temporary file
        temp_banks_file = f"temp_banks_megarun_{current_megarun}.yaml"
        self.bank_config_agent.save_bank_configuration(bank_config, temp_banks_file)
        
        logger.info(f"Megarun {current_megarun} hypothesis: {hypothesis.hypothesis}")
        
        # Update state
        state["current_bank_config"] = bank_config
        state["tested_hypotheses"].append({
            "megarun": current_megarun,
            "hypothesis": hypothesis.hypothesis,
            "expected_outcome": hypothesis.expected_outcome,
            "rationale": hypothesis.rationale,
            "configuration_changes": hypothesis.configuration_changes
        })
        
        return state
        
    async def run_subgraph_simulation(self, state: MetaSimulationState) -> MetaSimulationState:
        """Run the subgraph simulation with current configuration."""
        current_megarun = state["current_megarun"]
        logger.info(f"Running subgraph simulation for megarun {current_megarun}...")
        
        # Create temporary config files for this megarun
        temp_config_file = f"temp_config_megarun_{current_megarun}.yaml"
        temp_banks_file = f"temp_banks_megarun_{current_megarun}.yaml"
        
        # Write current configuration
        with open(temp_config_file, 'w') as f:
            yaml.dump(state["base_config"], f)
        
        # The bank config was already saved in prepare_bank_configuration
        
        try:
            # Create and run subgraph simulation
            subgraph_sim = LoanMarketSimulation(temp_config_file, temp_banks_file)
            subgraph_result = await subgraph_sim.run()
            
            # Extract market outcomes from subgraph state
            market_outcomes = self.megarun_lessons_agent._extract_market_outcomes({
                "market_log": subgraph_result.get("market_log", [])
            })
            
            # Collect results
            megarun_result = {
                "megarun_number": current_megarun,
                "market_configuration": self.megarun_lessons_agent._analyze_market_configuration(
                    state["current_bank_config"]
                ),
                "market_outcomes": market_outcomes,
                "subgraph_state": subgraph_result,
                "hypothesis": state["tested_hypotheses"][-1] if state["tested_hypotheses"] else None
            }
            
            state["megarun_results"].append(megarun_result)
            
        finally:
            # Cleanup temporary files
            for temp_file in [temp_config_file, temp_banks_file]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    
        logger.info(f"Completed subgraph simulation for megarun {current_megarun}")
        return state
        
    async def extract_megarun_lessons(self, state: MetaSimulationState) -> MetaSimulationState:
        """Extract macro-level lessons from the completed megarun."""
        current_megarun = state["current_megarun"]
        logger.info(f"=== STARTING LESSONS EXTRACTION for megarun {current_megarun} ===")
        
        try:
            # Get the latest megarun result
            latest_result = state["megarun_results"][-1]
            logger.info(f"Got latest megarun result for megarun {current_megarun}")
            
            # Get historical context
            logger.info("Getting historical lessons...")
            historical_lessons = self.memory_store.get_historical_megarun_patterns()
            logger.info(f"Retrieved {len(historical_lessons)} historical lesson patterns")
            
            # Extract lessons
            logger.info("Starting AI lessons extraction...")
            lessons, hypothesis_result, report = await self.megarun_lessons_agent.extract_megarun_lessons(
                current_megarun,
                latest_result["subgraph_state"],
                state["current_bank_config"],
                latest_result["hypothesis"],
                historical_lessons
            )
            logger.info(f"AI lessons extraction completed - got {len(lessons)} lessons")
            
            # Save megarun report
            os.makedirs("data", exist_ok=True)
            with open(f"data/megarun_{current_megarun}_report.md", "w") as f:
                f.write(report)
            logger.info(f"Saved data/megarun_{current_megarun}_report.md")
            
            # Store lessons in memory
            meta_sim_id = state.get("meta_simulation_id")
            if meta_sim_id:
                lesson_dicts = [
                    {
                        "lesson_type": lesson.lesson_type,
                        "lesson_text": lesson.lesson_text,
                        "confidence": lesson.confidence,
                        "market_configuration": lesson.market_configuration
                    }
                    for lesson in lessons
                ]
                
                self.memory_store.store_megarun_lessons(
                    meta_sim_id, current_megarun, lesson_dicts, latest_result["hypothesis"]
                )
                logger.info(f"Stored {len(lesson_dicts)} lessons in memory store")
            
            # Update state
            state["megarun_lessons"].append(report)
            if hypothesis_result:
                state["hypothesis_results"].append({
                    "megarun": current_megarun,
                    "hypothesis": hypothesis_result.hypothesis,
                    "result": hypothesis_result.result,
                    "confidence": hypothesis_result.confidence,
                    "evidence": hypothesis_result.evidence
                })
            
            # Update result with hypothesis result
            latest_result["hypothesis_result"] = {
                "hypothesis": hypothesis_result.hypothesis if hypothesis_result else "",
                "result": hypothesis_result.result if hypothesis_result else "",
                "confidence": hypothesis_result.confidence if hypothesis_result else 0,
                "evidence": hypothesis_result.evidence if hypothesis_result else ""
            }
            
            logger.info(f"=== COMPLETED LESSONS EXTRACTION for megarun {current_megarun} - {len(lessons)} lessons ===")
            
            # Increment megarun counter after successful completion
            state["current_megarun"] = current_megarun + 1
            logger.info(f"Incremented megarun counter to {state['current_megarun']}")
            
            return state
            
        except Exception as e:
            logger.error(f"ERROR in extract_megarun_lessons for megarun {current_megarun}: {e}", exc_info=True)
            raise
        
    def check_meta_continuation(self, state: MetaSimulationState) -> str:
        """Check if we should continue with more megaruns or end."""
        current_megarun = state["current_megarun"]
        total_megaruns = state["total_megaruns"]
        
        if current_megarun >= total_megaruns:
            logger.info("All megaruns completed, proceeding to final synthesis")
            return "end"
        else:
            logger.info(f"Megarun {current_megarun} complete, will continue to next megarun")
            return "continue"
            
    async def synthesize_final_lessons(self, state: MetaSimulationState) -> MetaSimulationState:
        """Synthesize final lessons across all megaruns."""
        logger.info("Synthesizing final lessons across all megaruns...")
        
        # Generate final synthesis
        insights, final_report = await self.synthesis_agent.synthesize_final_lessons(
            state["megarun_results"],
            state["megarun_lessons"],
            state["hypothesis_results"]
        )
        
        # Save final report
        with open("data/meta_simulation_final_report.md", "w") as f:
            f.write(final_report)
        logger.info("Saved data/meta_simulation_final_report.md")
        
        # Update meta-simulation in database
        meta_sim_id = state.get("meta_simulation_id")
        if meta_sim_id:
            self.memory_store.update_meta_simulation_synthesis(meta_sim_id, final_report)
        
        state["final_synthesis"] = final_report
        
        logger.info(f"Generated {len(insights)} synthesis insights")
        return state
        
    async def run(self) -> Dict:
        """Run the complete meta-simulation."""
        logger.info(f"Starting meta-simulation with {self.total_megaruns} megaruns...")
        
        initial_state = {
            "current_megarun": 0,
            "total_megaruns": self.total_megaruns,
            "base_config": self.full_base_config,
            "current_bank_config": {},
            "megarun_results": [],
            "megarun_lessons": [],
            "final_synthesis": None,
            "tested_hypotheses": [],
            "hypothesis_results": [],
            "meta_simulation_id": None
        }
        
        # Configure with recursion limit
        config = {"recursion_limit": 250}
        final_state = await self.graph.ainvoke(initial_state, config=config)
        
        logger.info("Meta-simulation completed successfully!")
        return final_state