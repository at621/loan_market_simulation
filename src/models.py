"""Data models and types for the loan market simulation."""

from dataclasses import dataclass
from typing import Dict, List, Optional, TypedDict, Annotated
from typing_extensions import TypedDict
from enum import Enum
import pandas as pd
from langgraph.graph import add_messages

def merge_bank_decisions(left: Dict[str, Dict], right: Dict[str, Dict]) -> Dict[str, Dict]:
    """Merge bank decisions dictionaries."""
    if left is None:
        left = {}
    if right is None:
        right = {}
    return {**left, **right}


class BankStrategy(Enum):
    GROW = "Grow"
    MAINTAIN = "Maintain"


@dataclass
class Consumer:
    """Consumer entity with loan preferences."""
    id: str
    rate_sensitivity: float  # 0-1, higher = more rate sensitive
    image_weight: float  # 0-1, normalized weight
    speed_weight: float  # 0-1, normalized weight
    rate_weight: float  # 1 - image_weight - speed_weight
    loan_size: float  # Loan amount they want
    
    def calculate_utility(self, rate_score: float, image_score: float, 
                         execution_speed: float) -> float:
        """Calculate utility for a bank offer."""
        # Apply rate sensitivity to rate score
        adjusted_rate_score = rate_score ** (1 + self.rate_sensitivity)
        
        # Weighted sum of factors
        utility = (
            self.rate_weight * adjusted_rate_score +
            self.image_weight * image_score +
            self.speed_weight * execution_speed
        )
        return utility


@dataclass
class Bank:
    """Bank entity with attributes and financials."""
    id: str
    strategy: BankStrategy
    image_score: float  # 0-1
    execution_speed: float  # 0-1
    cost_of_funds_bps: int
    operating_cost_per_loan: float
    initial_equity: float
    initial_portfolio_balance: float
    

@dataclass
class Loan:
    """Individual loan record."""
    loan_id: str
    consumer_id: str
    bank_id: str
    principal_start: float
    interest_rate_bps: int
    round_added: int
    principal_outstanding: float
    is_active: bool


@dataclass
class BankFinancials:
    """Bank's financial state at a point in time."""
    bank_id: str
    round: int
    equity: float
    portfolio_balance: float
    new_loan_volume: float
    new_loan_count: int
    gross_interest_income: float
    interest_expense: float
    net_interest_income: float
    operating_cost: float
    profit: float
    roe: float
    is_bankrupt: bool


@dataclass
class MarketSnapshot:
    """Market state at the end of a round."""
    round: int
    offered_rates: Dict[str, int]  # bank_id -> rate_bps
    new_volumes: Dict[str, float]  # bank_id -> volume
    new_counts: Dict[str, int]  # bank_id -> count
    profits: Dict[str, float]  # bank_id -> profit
    equities: Dict[str, float]  # bank_id -> equity
    bankruptcies: List[str]  # list of bankrupt bank_ids


class SimulationState(TypedDict):
    """Complete simulation state for LangGraph."""
    # Round tracking
    current_round: int
    
    # Static entity data
    consumers: pd.DataFrame
    banks: pd.DataFrame
    
    # Market history for AI agents
    market_history: List[MarketSnapshot]
    
    # Current round market state
    active_bank_ids: List[str]
    bank_decisions: Annotated[Dict[str, Dict], merge_bank_decisions]  # Accumulates individual decisions
    market_rates: Dict[str, int]  # Final merged rates
    
    # Portfolio and financials
    portfolio_ledger: pd.DataFrame
    bank_financials: Dict[str, BankFinancials]  # Current state
    start_portfolio_balances: Dict[str, float]  # Portfolio balances before amortization
    
    # Round results
    consumer_allocations: Dict[str, Optional[str]]  # consumer_id -> bank_id or None
    round_summary: MarketSnapshot
    
    # Outputs
    market_log: List[Dict]
    
    # For lessons learned (populated after all rounds)
    summary_content: Optional[str]  # Content from summary.md
    initial_bank_configs: Optional[List[Dict]]  # Initial bank configurations
    lessons_content: Optional[str]  # Generated lessons learned content


class MetaSimulationState(TypedDict):
    """State for meta-simulation that runs multiple subgraph instances."""
    # Meta-simulation tracking
    current_megarun: int
    total_megaruns: int
    
    # Configuration management
    base_config: Dict  # Base simulation config
    current_bank_config: Dict  # Current banks configuration for this megarun
    
    # Megarun results
    megarun_results: List[Dict]  # Results from each completed megarun
    megarun_lessons: List[str]  # Lessons from each megarun
    
    # Final outputs
    final_synthesis: Optional[str]  # Cross-megarun analysis
    
    # Hypotheses tracking
    tested_hypotheses: List[Dict]  # Hypotheses tested in each megarun
    hypothesis_results: List[Dict]  # Results of hypothesis testing


class BankDecisionState(TypedDict):
    """Substate for individual bank decision."""
    bank_id: str
    bank_info: Dict  # Strategy, financials, etc.
    market_context: Dict  # History, competitor info
    decision: Optional[Dict]  # Rate and reasoning


@dataclass
class BankDecision:
    """AI agent's decision for a bank."""
    bank_id: str
    rate_bps: int
    reasoning: str
    expected_outcome: str
    previous_decision_evaluation: Optional[str] = None
    previous_decision_score: Optional[int] = None
    
    def validate(self) -> bool:
        """Validate the decision is within bounds."""
        return 100 <= self.rate_bps <= 1000