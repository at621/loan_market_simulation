"""Main simulation implementation using LangGraph with AI agents."""

import asyncio
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send
import yaml
import logging
from datetime import datetime
import uuid

from src.models import (
    SimulationState,
    BankDecisionState,
    Bank,
    Consumer,
    Loan,
    BankFinancials,
    MarketSnapshot,
    BankDecision,
    BankStrategy,
)
import os
from src.consumer_logic import ConsumerDecisionEngine
from src.financial_calculator import FinancialCalculator

# Require OpenAI API key
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable is required. Please set your OpenAI API key.")

from agents.bank_agent import BankAgent
from agents.summary_agent import SummaryAgent
from agents.lessons_agent import LessonsAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_output_directory(base_dir: str = "data", suffix: str = "") -> str:
    """Create a timestamped output directory for this simulation run."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if suffix:
        dir_name = f"{timestamp}_{suffix}"
    else:
        dir_name = timestamp
    
    output_dir = os.path.join(base_dir, dir_name)
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Created output directory: {output_dir}")
    return output_dir


class LoanMarketSimulation:
    """Main simulation orchestrator using LangGraph."""

    def __init__(self, config_path: str = "config/config.yaml", banks_config_path: str = "config/initialise_banks.yaml", output_dir: str = None, file_prefix: str = "", create_output_dir: bool = True):
        """Initialize simulation with configuration."""
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        
        # Load bank configuration from separate file
        with open(banks_config_path, "r") as f:
            banks_config = yaml.safe_load(f)
            self.config.update(banks_config)

        self.seed = self.config["seed"]
        np.random.seed(self.seed)
        
        # Set output directory
        if create_output_dir and output_dir is None:
            # Only create directory if not provided (standalone simulation)
            self.output_dir = create_output_directory(base_dir="data", suffix="sim")
        elif output_dir is not None:
            # Use provided directory (meta-simulation case)
            self.output_dir = output_dir
        else:
            # No output directory needed (temp simulation for graph creation)
            self.output_dir = None
        
        # Set file prefix for output files
        self.file_prefix = file_prefix

        # Initialize components
        self.bank_agent = BankAgent(self.config["ai_agent_params"])
        self.consumer_engine = ConsumerDecisionEngine()
        self.financial_calc = FinancialCalculator()
        self.summary_agent = SummaryAgent(self.config["ai_agent_params"])
        self.lessons_agent = LessonsAgent(
            model_name=self.config.get("ai_agent_params", {}).get("model_name", "gpt-4o"),
            temperature=self.config.get("ai_agent_params", {}).get("temperature", 0.3)
        )

        # Build the graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        builder = StateGraph(SimulationState)

        # Add nodes
        builder.add_node("initialize", self.initialize_simulation)
        builder.add_node("broadcast_market", self.broadcast_market_state)
        builder.add_node("bank_agent_decision", self.bank_agent_decision)
        builder.add_node("merge_decisions", self.merge_bank_decisions)
        builder.add_node("consumer_decisions", self.consumer_decision_phase)
        builder.add_node("calculate_financials", self.calculate_financials)
        builder.add_node("record_round", self.record_round_results)
        builder.add_node("generate_summary", self.generate_summary)
        builder.add_node("extract_lessons", self.extract_lessons)

        # Add edges
        builder.add_edge(START, "initialize")
        builder.add_edge("initialize", "broadcast_market")

        # Use Send API for parallel bank decisions
        builder.add_conditional_edges(
            "broadcast_market", self.route_to_bank_agents, ["bank_agent_decision"]
        )

        builder.add_edge("bank_agent_decision", "merge_decisions")
        builder.add_edge("merge_decisions", "consumer_decisions")
        builder.add_edge("consumer_decisions", "calculate_financials")
        builder.add_edge("calculate_financials", "record_round")

        # Loop or end
        builder.add_conditional_edges(
            "record_round",
            self.check_continuation,
            {"continue": "broadcast_market", "end": "generate_summary"},
        )

        builder.add_edge("generate_summary", "extract_lessons")
        builder.add_edge("extract_lessons", END)

        return builder.compile()

    def initialize_simulation(self, state: SimulationState) -> SimulationState:
        """Initialize simulation entities and portfolio."""
        logger.info("Initializing simulation...")

        # Generate consumers
        consumers_df = self._generate_consumers()

        # Generate banks
        banks_df = self._generate_banks()

        # Initialize portfolio ledger with pre-existing loans
        portfolio_ledger = self._initialize_portfolio(banks_df, consumers_df)
        

        # Initialize bank financials
        bank_financials = {}
        for _, bank in banks_df.iterrows():
            bank_financials[bank["id"]] = BankFinancials(
                bank_id=bank["id"],
                round=0,
                equity=bank["equity_start"],
                portfolio_balance=bank["portfolio_balance_start"],
                new_loan_volume=0,
                new_loan_count=0,
                gross_interest_income=0,
                interest_expense=0,
                net_interest_income=0,
                operating_cost=0,
                profit=0,
                roe=0,
                is_bankrupt=False,
            )

        # Store initial bank configurations
        initial_bank_configs = []
        for _, bank in banks_df.iterrows():
            initial_bank_configs.append({
                "name": bank["id"],
                "strategy": bank["strategy"].value if hasattr(bank["strategy"], "value") else bank["strategy"],
                "equity": bank["equity_start"],
                "image_score": bank["image_score"],
                "execution_speed": bank["execution_speed"],
                "cost_of_funds_bps": bank["cost_of_funds_bps"],
                "operating_cost_per_loan": bank["operating_cost_per_loan"],
                "initial_portfolio_balance": bank["portfolio_balance_start"]
            })

        return {
            "current_round": 0,
            "consumers": consumers_df,
            "banks": banks_df,
            "market_history": [],
            "active_bank_ids": banks_df["id"].tolist(),
            "bank_decisions": {},
            "market_rates": {},
            "portfolio_ledger": portfolio_ledger,
            "bank_financials": bank_financials,
            "consumer_allocations": {},
            "round_summary": None,
            "market_log": [],
            "start_portfolio_balances": {},
            "initial_bank_configs": initial_bank_configs,
            "summary_content": None,
            "lessons_content": None,
        }

    def _generate_consumers(self) -> pd.DataFrame:
        """Generate consumer population with attributes."""
        n = self.config["customer_params"]["count"]
        alpha = self.config["customer_params"]["attribute_dist"]["alpha"]
        beta = self.config["customer_params"]["attribute_dist"]["beta"]

        # Generate attributes from Beta distribution
        rate_sensitivities = np.random.beta(alpha, beta, n)
        image_weights_raw = np.random.beta(alpha, beta, n)
        speed_weights_raw = np.random.beta(alpha, beta, n)

        # Normalize weights to sum to 1
        weight_sums = image_weights_raw + speed_weights_raw
        image_weights = image_weights_raw / (weight_sums + 1)
        speed_weights = speed_weights_raw / (weight_sums + 1)
        rate_weights = 1 - image_weights - speed_weights

        # Generate loan sizes from LogNormal
        mean = self.config["customer_params"]["loan_size_dist"]["mean"]
        sigma = self.config["customer_params"]["loan_size_dist"]["sigma"]
        loan_sizes = np.random.lognormal(np.log(mean), sigma / mean, n)

        consumers_df = pd.DataFrame(
            {
                "id": [f"C{i:03d}" for i in range(n)],
                "rate_sensitivity": rate_sensitivities,
                "image_weight": image_weights,
                "speed_weight": speed_weights,
                "rate_weight": rate_weights,
                "loan_size": loan_sizes,
            }
        )

        return consumers_df

    def _generate_consumers_for_round(self, state: SimulationState) -> pd.DataFrame:
        """Generate consumers for a round based on amortization flow with fixed loan sizes."""
        # Calculate total amortization flow from this round
        total_amortization = 0
        amortization_years = self.config["simulation_params"]["amortization_years"]
        
        # Sum up amortization from all active loans
        active_loans = state["portfolio_ledger"][state["portfolio_ledger"]["is_active"] == True]
        if not active_loans.empty:
            total_amortization = (active_loans["principal_start"] / amortization_years).sum()
        
        # Use fixed loan size from config
        fixed_loan_size = self.config["customer_params"]["loan_size_dist"]["mean"]
        
        # Calculate number of consumers needed to match amortization flow
        if total_amortization > 0 and fixed_loan_size > 0:
            num_consumers = max(1, int(round(total_amortization / fixed_loan_size)))
        else:
            # Fallback to original consumer count if no amortization
            num_consumers = self.config["customer_params"]["count"]
        
        logger.info(f"Round {state['current_round']}: Total amortization ${total_amortization:,.0f}, "
                   f"generating {num_consumers} consumers with ${fixed_loan_size:,.0f} fixed loan size")
        
        # Generate consumer attributes (same as original but with fixed loan size)
        alpha = self.config["customer_params"]["attribute_dist"]["alpha"]
        beta = self.config["customer_params"]["attribute_dist"]["beta"]

        # Generate attributes from Beta distribution
        rate_sensitivities = np.random.beta(alpha, beta, num_consumers)
        image_weights_raw = np.random.beta(alpha, beta, num_consumers)
        speed_weights_raw = np.random.beta(alpha, beta, num_consumers)

        # Normalize weights to sum to 1
        weight_sums = image_weights_raw + speed_weights_raw
        image_weights = image_weights_raw / (weight_sums + 1)
        speed_weights = speed_weights_raw / (weight_sums + 1)
        rate_weights = 1 - image_weights - speed_weights

        # Use fixed loan size for all consumers
        loan_sizes = np.full(num_consumers, fixed_loan_size)

        consumers_df = pd.DataFrame(
            {
                "id": [f"C{state['current_round']:02d}_{i:03d}" for i in range(num_consumers)],
                "rate_sensitivity": rate_sensitivities,
                "image_weight": image_weights,
                "speed_weight": speed_weights,
                "rate_weight": rate_weights,
                "loan_size": loan_sizes,
            }
        )

        return consumers_df

    def _build_portfolio_history(self, state: SimulationState) -> List[Dict[str, float]]:
        """Build portfolio balance history from market log for consumer utility calculations."""
        portfolio_history = []
        
        # Extract portfolio balance data from market log
        for entry in state["market_log"]:
            round_data = {}
            # Group by round to get all banks' portfolio balances for each round
            current_round = entry["round"]
            
            # Find all entries for this round
            round_entries = [e for e in state["market_log"] if e["round"] == current_round]
            
            for round_entry in round_entries:
                bank_id = round_entry["bank_id"]
                portfolio_balance = round_entry.get("portfolio_balance_start", 0.0)
                round_data[bank_id] = portfolio_balance
            
            # Only add if we have data for this round and it's not already added
            if round_data and not any(rd == round_data for rd in portfolio_history):
                portfolio_history.append(round_data)
        
        # If no history yet, use current start balances
        if not portfolio_history and "start_portfolio_balances" in state:
            portfolio_history.append(state["start_portfolio_balances"].copy())
        
        return portfolio_history

    def _calculate_bank_capacities(self, state: SimulationState) -> Dict[str, float]:
        """Calculate each bank's available lending capacity (10x equity - current portfolio)."""
        bank_capacities = {}
        
        for bank_id in state["active_bank_ids"]:
            # Get current equity
            current_equity = state["bank_financials"][bank_id].equity
            
            # Get current portfolio balance
            bank_portfolio = state["portfolio_ledger"][
                (state["portfolio_ledger"]["bank_id"] == bank_id) &
                (state["portfolio_ledger"]["is_active"] == True)
            ]
            current_portfolio = bank_portfolio["principal_outstanding"].sum()
            
            # Calculate maximum allowed portfolio (10x equity)
            max_portfolio = current_equity * 10
            
            # Available capacity is the difference
            available_capacity = max(0, max_portfolio - current_portfolio)
            bank_capacities[bank_id] = available_capacity
            
            logger.info(f"Bank {bank_id} capacity: ${current_equity:,.0f} equity * 10 = "
                       f"${max_portfolio:,.0f} max, ${current_portfolio:,.0f} current, "
                       f"${available_capacity:,.0f} available")
        
        return bank_capacities

    def _generate_banks(self) -> pd.DataFrame:
        """Generate bank population from individual configurations."""
        banks_data = []
        individual_banks = self.config["bank_params"]["individual_banks"]
        defaults = self.config["bank_params"].get("default_conditions", {})
        
        # Create banks from individual configurations
        for bank_id, bank_config in individual_banks.items():
            # Use individual config with defaults as fallback
            bank_data = {
                "id": bank_id,
                "name": bank_config.get("name", bank_id),
                "strategy": bank_config.get("strategy", "Maintain"),
                "size_category": bank_config.get("size_category", "medium"),
                "image_score": bank_config.get("image_score", np.random.uniform(0.4, 0.8)),
                "execution_speed": bank_config.get("execution_speed", np.random.uniform(0.6, 0.9)),
                "cost_of_funds_bps": bank_config.get("cost_of_funds_bps", defaults.get("cost_of_funds_bps", 300)),
                "operating_cost_per_loan": bank_config.get("operating_cost_per_loan", defaults.get("operating_cost_per_loan", 1000)),
                "equity_start": bank_config.get("equity_start", defaults.get("equity_start", 10000000)),
                "portfolio_balance_start": bank_config.get("portfolio_balance_start", defaults.get("portfolio_balance_start", 100000000)),
                "portfolio_rate_start_bps": bank_config.get("portfolio_rate_start_bps", defaults.get("portfolio_rate_start_bps", 500)),
            }
            banks_data.append(bank_data)
        
        # Create DataFrame
        banks_df = pd.DataFrame(banks_data)
        
        # Log bank setup
        logger.info("Bank Setup:")
        for _, bank in banks_df.iterrows():
            logger.info(f"  {bank['id']} ({bank['name']}): {bank['strategy']} strategy, "
                       f"${bank['portfolio_balance_start']:,.0f} portfolio, "
                       f"${bank['equity_start']:,.0f} equity, "
                       f"{bank['portfolio_rate_start_bps']} bps initial rate")
        
        return banks_df

    def _initialize_portfolio(
        self, banks_df: pd.DataFrame, consumers_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Create initial loan portfolio before round 1."""
        loans = []
        loan_counter = 0

        mean_loan_size = self.config["customer_params"]["loan_size_dist"]["mean"]
        loan_size_sigma = self.config["customer_params"]["loan_size_dist"]["sigma"]

        for _, bank in banks_df.iterrows():
            bank_name = bank.get("name", bank["id"])
            target_balance = bank["portfolio_balance_start"]
            bank_rate = bank["portfolio_rate_start_bps"]
            
            # Estimate number of loans needed
            estimated_n_loans = int(target_balance / mean_loan_size)
            
            # Generate loan sizes using same distribution as consumers
            # This ensures realistic loan size distribution
            loan_sizes = np.random.lognormal(
                np.log(mean_loan_size), 
                loan_size_sigma / mean_loan_size, 
                estimated_n_loans
            )
            
            # Adjust to match target balance exactly
            current_total = loan_sizes.sum()
            if current_total > 0:
                adjustment_factor = target_balance / current_total
                loan_sizes = loan_sizes * adjustment_factor
            
            # Randomly select consumers for these loans (with replacement)
            selected_consumers = np.random.choice(
                consumers_df["id"].values, size=len(loan_sizes), replace=True
            )
            
            # Create individual loan records
            for i, (consumer_id, loan_amount) in enumerate(zip(selected_consumers, loan_sizes)):
                loans.append(
                    {
                        "loan_id": f"L{loan_counter:06d}",
                        "consumer_id": consumer_id,
                        "bank_id": bank["id"],
                        "principal_start": loan_amount,
                        "interest_rate_bps": bank_rate,  # Each bank's specific starting rate
                        "round_added": 0,
                        "principal_outstanding": loan_amount,
                        "is_active": True,
                    }
                )
                loan_counter += 1
            
            # Log portfolio creation
            actual_balance = sum(loan_sizes)
            logger.info(
                f"  Created {len(loan_sizes)} initial loans for {bank['id']} ({bank_name}): "
                f"${actual_balance:,.0f} total at {bank_rate} bps"
            )

        portfolio_df = pd.DataFrame(loans)
        
        # Verify portfolio totals
        logger.info("\nInitial Portfolio Summary:")
        for bank_id in banks_df["id"]:
            bank_portfolio = portfolio_df[portfolio_df["bank_id"] == bank_id]
            total_balance = bank_portfolio["principal_outstanding"].sum()
            avg_loan_size = bank_portfolio["principal_outstanding"].mean()
            logger.info(
                f"  {bank_id}: {len(bank_portfolio)} loans, "
                f"${total_balance:,.0f} total, "
                f"${avg_loan_size:,.0f} avg loan size"
            )
            

        return portfolio_df

    def broadcast_market_state(self, state: SimulationState) -> SimulationState:
        """Prepare market context for bank agents."""
        state["current_round"] += 1
        logger.info(f"Starting round {state['current_round']}")
        
        # Update active bank list - exclude banks with zero portfolio balance or bankruptcy
        active_banks = []
        for bank_id in state["banks"]["id"]:
            # Check if bank is bankrupt
            if state["bank_financials"][bank_id].is_bankrupt:
                continue
                
            # Check if bank has zero portfolio balance (cannot originate loans)
            bank_portfolio = state["portfolio_ledger"][
                (state["portfolio_ledger"]["bank_id"] == bank_id) &
                (state["portfolio_ledger"]["is_active"] == True)
            ]
            portfolio_balance = bank_portfolio["principal_outstanding"].sum()
            
            if portfolio_balance <= 0:
                logger.info(f"Bank {bank_id} excluded from loan origination: zero portfolio balance")
                continue
                
            active_banks.append(bank_id)
        
        state["active_bank_ids"] = active_banks
        state["bank_decisions"] = {}
        logger.info(f"Active banks for round {state['current_round']}: {len(active_banks)} banks - {active_banks}")
        return state

    def route_to_bank_agents(self, state: SimulationState) -> List[Send]:
        """Send parallel tasks to each active bank."""
        sends = []

        for bank_id in state["active_bank_ids"]:
            bank_info = self._get_bank_info(state, bank_id)
            market_context = self._get_market_context(state)

            sends.append(
                Send(
                    "bank_agent_decision",
                    {
                        "bank_id": bank_id,
                        "bank_info": bank_info,
                        "market_context": market_context,
                        "decision": None,
                    },
                )
            )

        return sends

    def _get_bank_info(self, state: SimulationState, bank_id: str) -> Dict:
        """Extract bank-specific information."""
        bank_row = state["banks"][state["banks"]["id"] == bank_id].iloc[0]
        financials = state["bank_financials"][bank_id]


        # Calculate bank-specific metrics
        portfolio = state["portfolio_ledger"][
            (state["portfolio_ledger"]["bank_id"] == bank_id)
            & (state["portfolio_ledger"]["is_active"])
        ]
        
        # Count active loans
        active_loan_count = len(portfolio)
        portfolio_balance = portfolio["principal_outstanding"].sum()
        
        # Calculate average rate on existing portfolio
        if active_loan_count > 0:
            avg_portfolio_rate = (portfolio["principal_outstanding"] * portfolio["interest_rate_bps"]).sum() / portfolio_balance
        else:
            avg_portfolio_rate = 0

        # Calculate market share from last round
        last_market_share = 0
        if state["market_history"]:
            last_round = state["market_history"][-1]
            total_volume = sum(last_round.new_volumes.values())
            if total_volume > 0:
                last_market_share = (last_round.new_volumes.get(bank_id, 0) / total_volume) * 100
        
        bank_info = {
            "bank_id": bank_id,
            "strategy": bank_row["strategy"],
            "image_score": bank_row["image_score"],
            "execution_speed": bank_row["execution_speed"],
            "cost_of_funds_bps": bank_row["cost_of_funds_bps"],
            "operating_cost_per_loan": bank_row["operating_cost_per_loan"],
            "current_equity": financials.equity,
            "portfolio_balance": portfolio_balance,
            "active_loan_count": active_loan_count,
            "avg_portfolio_rate": avg_portfolio_rate,
            "last_profit": financials.profit,
            "last_roe": financials.roe,
            "last_new_loan_volume": financials.new_loan_volume,
            "last_new_loan_count": financials.new_loan_count,
            "last_market_share": last_market_share,
            "round": state["current_round"],
        }
        
        # Add competitor intelligence
        competitor_info = self._get_competitor_intelligence(state, bank_id)
        bank_info.update(competitor_info)
        
        # Log detailed bank input data with competitor intelligence
        bank_name = bank_row.get("name", bank_id)
        logger.info(f"""
Bank {bank_id} ({bank_name}) Decision Input:
  Strategy: {bank_info['strategy']}
  Current Equity: ${bank_info['current_equity']:,.0f}
  Portfolio Balance: ${bank_info['portfolio_balance']:,.0f}
  Active Loans: {bank_info['active_loan_count']}
  Avg Portfolio Rate: {bank_info['avg_portfolio_rate']:.0f} bps
  Last Round Profit: ${bank_info['last_profit']:,.0f}
  Last Round ROE: {bank_info['last_roe']:.1%}
  Last Round New Loans: {bank_info['last_new_loan_count']} (${bank_info['last_new_loan_volume']:,.0f})
  Cost of Funds: {bank_info['cost_of_funds_bps']} bps
  Image Score: {bank_info['image_score']:.2f}
  Execution Speed: {bank_info['execution_speed']:.2f}

COMPETITOR INTELLIGENCE:
{bank_info['competitor_summary']}

RECENT PRICING HISTORY:
{bank_info['pricing_history']}""")
        
        return bank_info

    def _get_competitor_intelligence(self, state: SimulationState, bank_id: str) -> Dict:
        """Get detailed competitor intelligence for a bank."""
        competitor_data = []
        pricing_history = []
        
        # Get all other banks' current state
        for competitor_id in state["banks"]["id"]:
            if competitor_id == bank_id:
                continue
                
            # Get competitor's current financials
            comp_financials = state["bank_financials"][competitor_id]
            comp_bank_row = state["banks"][state["banks"]["id"] == competitor_id].iloc[0]
            
            # Get competitor's portfolio
            comp_portfolio = state["portfolio_ledger"][
                (state["portfolio_ledger"]["bank_id"] == competitor_id) &
                (state["portfolio_ledger"]["is_active"])
            ]
            
            comp_portfolio_balance = comp_portfolio["principal_outstanding"].sum()
            comp_active_loans = len(comp_portfolio)
            
            # Calculate competitor's average portfolio rate
            if comp_active_loans > 0:
                comp_avg_rate = (comp_portfolio["principal_outstanding"] * comp_portfolio["interest_rate_bps"]).sum() / comp_portfolio_balance
            else:
                comp_avg_rate = 0
            
            competitor_data.append({
                "id": competitor_id,
                "name": comp_bank_row.get("name", competitor_id),
                "strategy": comp_bank_row["strategy"],
                "equity": comp_financials.equity,
                "portfolio_balance": comp_portfolio_balance,
                "active_loans": comp_active_loans,
                "avg_portfolio_rate": comp_avg_rate,
                "last_profit": comp_financials.profit,
                "last_roe": comp_financials.roe,
                "last_new_loans": comp_financials.new_loan_count,
                "last_new_volume": comp_financials.new_loan_volume,
                "is_bankrupt": comp_financials.is_bankrupt,
                "image_score": comp_bank_row["image_score"],
                "execution_speed": comp_bank_row["execution_speed"]
            })
        
        # Format competitor summary
        active_competitors = [c for c in competitor_data if not c["is_bankrupt"]]
        bankrupt_competitors = [c for c in competitor_data if c["is_bankrupt"]]
        
        comp_summary_lines = []
        
        # Active competitors sorted by equity
        active_competitors.sort(key=lambda x: x["equity"], reverse=True)
        comp_summary_lines.append("  ACTIVE COMPETITORS (by equity):")
        for comp in active_competitors[:5]:  # Top 5 competitors
            market_share = (comp["last_new_volume"] / max(1, sum(c["last_new_volume"] for c in active_competitors))) * 100
            comp_summary_lines.append(
                f"    {comp['id']} ({comp['name']}, {comp['strategy']}): ${comp['equity']:,.0f} equity, "
                f"{comp['active_loans']} loans, ROE {comp['last_roe']:.1%}, "
                f"last round {comp['last_new_loans']} new loans ({market_share:.1f}% share)"
            )
        
        if bankrupt_competitors:
            bankrupt_names = [f"{c['id']} ({c['name']})" for c in bankrupt_competitors]
            comp_summary_lines.append(f"  BANKRUPT: {', '.join(bankrupt_names)}")
        
        # Get current market rates and pricing history
        pricing_lines = []
        if len(state["market_history"]) > 0:
            # Show current round market rates first
            last_round = state["market_history"][-1]
            current_rates = last_round.offered_rates
            current_market_avg = sum(current_rates.values()) / len(current_rates)
            
            pricing_lines.append("  CURRENT MARKET RATES (Last Round):")
            pricing_lines.append(f"    Market Average: {current_market_avg:.0f} bps")
            
            # Sort current rates to show competitive positioning
            current_rates_sorted = sorted(current_rates.items(), key=lambda x: x[1])
            for comp_id, rate in current_rates_sorted:
                volume = last_round.new_volumes.get(comp_id, 0)
                count = last_round.new_counts.get(comp_id, 0)
                is_self = " (YOU)" if comp_id == bank_id else ""
                pricing_lines.append(f"      {comp_id}: {rate} bps ({count} loans, ${volume:,.0f}){is_self}")
            
            pricing_lines.append("")
            pricing_lines.append("  PRICING HISTORY (Last 3 Rounds):")
            # Show last 3 rounds of pricing data
            recent_rounds = state["market_history"][-3:]
            
            for round_data in recent_rounds:
                round_avg = sum(round_data.offered_rates.values()) / len(round_data.offered_rates)
                pricing_lines.append(f"    Round {round_data.round} (avg: {round_avg:.0f} bps):")
                # Sort by rate to show competitive positioning
                rates_sorted = sorted(round_data.offered_rates.items(), key=lambda x: x[1])
                for comp_id, rate in rates_sorted:
                    volume = round_data.new_volumes.get(comp_id, 0)
                    count = round_data.new_counts.get(comp_id, 0)
                    is_self = " (YOU)" if comp_id == bank_id else ""
                    pricing_lines.append(f"      {comp_id}: {rate} bps ({count} loans, ${volume:,.0f}){is_self}")
        
        return {
            "competitor_summary": "\n".join(comp_summary_lines),
            "pricing_history": "\n".join(pricing_lines),
            "active_competitors": active_competitors,
            "bankrupt_competitors": bankrupt_competitors,
            "competitor_rate_range": {
                "min": min([round_data.offered_rates[cid] for round_data in state["market_history"][-1:] for cid in round_data.offered_rates if cid != bank_id], default=0),
                "max": max([round_data.offered_rates[cid] for round_data in state["market_history"][-1:] for cid in round_data.offered_rates if cid != bank_id], default=0),
                "avg": sum([round_data.offered_rates[cid] for round_data in state["market_history"][-1:] for cid in round_data.offered_rates if cid != bank_id]) / max(1, len([cid for round_data in state["market_history"][-1:] for cid in round_data.offered_rates if cid != bank_id]))
            } if state["market_history"] else {"min": 0, "max": 0, "avg": 0}
        }

    def _get_market_context(self, state: SimulationState) -> Dict:
        """Extract market-wide context."""
        market_context = {
            "current_round": state["current_round"],
            "total_rounds": self.config["simulation_params"]["rounds"],
            "market_history": state["market_history"],
            "all_bank_strategies": {
                row["id"]: row["strategy"] for _, row in state["banks"].iterrows()
            },
            "consumer_params": self.config["customer_params"],
            "behavior_params": self.config["behavior_params"],
        }
        
        # Log market context once per round
        if len(state["market_history"]) > 0:
            last_round = state["market_history"][-1]
            avg_rate = sum(last_round.offered_rates.values()) / len(last_round.offered_rates) if last_round.offered_rates else 0
            total_volume = sum(last_round.new_volumes.values())
            bankruptcies = len(last_round.bankruptcies)
            
            logger.info(f"""
Market Context (Round {state['current_round']}):
  Last Round Avg Rate: {avg_rate:.0f} bps
  Last Round Total Volume: ${total_volume:,.0f}
  Current Bankruptcies: {bankruptcies}
  Active Banks: {len(state['active_bank_ids'])}
  Remaining Rounds: {market_context['total_rounds'] - state['current_round']}""")
        
        return market_context

    async def bank_agent_decision(self, state: BankDecisionState) -> Dict:
        """Individual bank AI agent makes rate decision."""
        try:
            decision = await self.bank_agent.make_decision(
                state["bank_info"], state["market_context"]
            )

            return {
                "bank_decisions": {
                    state["bank_id"]: {
                        "rate": decision.rate_bps,
                        "reasoning": decision.reasoning,
                        "expected_outcome": decision.expected_outcome,
                        "previous_decision_score": decision.previous_decision_score,
                    }
                }
            }
        except Exception as e:
            logger.error(f"Bank {state['bank_id']} decision failed: {e}", exc_info=True)
            print(f"ERROR: Bank {state['bank_id']} AI agent failed: {e}")
            print(f"Falling back to heuristic decision for Bank {state['bank_id']}")
            # Fallback to heuristic
            fallback_rate = self._calculate_fallback_rate(state)
            return {
                "bank_decisions": {
                    state["bank_id"]: {
                        "rate": fallback_rate,
                        "reasoning": f"Fallback due to error: {str(e)}",
                        "expected_outcome": "uncertain",
                        "previous_decision_score": None,
                    }
                }
            }

    def _calculate_fallback_rate(self, state: BankDecisionState) -> int:
        """Calculate fallback rate using simple heuristics."""
        # Implement the original heuristics from spec
        if state["bank_info"]["strategy"] == "Grow":
            if state["bank_info"]["last_profit"] > 0:
                # Simplified: use cost of funds + margin
                return state["bank_info"]["cost_of_funds_bps"] + 150
            else:
                return state["bank_info"]["cost_of_funds_bps"] + 200
        else:  # Maintain
            base_rate = state["bank_info"]["cost_of_funds_bps"] + 200
            walk = np.random.normal(
                0, self.config["behavior_params"]["maintain_walk_stdev_bps"]
            )
            return int(base_rate + walk)

    def merge_bank_decisions(self, state: SimulationState) -> SimulationState:
        """Merge all bank decisions into market rates."""
        market_rates = {}

        for bank_id, decision in state["bank_decisions"].items():
            # Validate and bound the rate
            rate = decision["rate"]
            rate = max(100, min(1000, rate))
            market_rates[bank_id] = rate

            logger.info(
                f"Bank {bank_id} set rate: {rate} bps - {decision['reasoning'][:150]}..."
            )

        state["market_rates"] = market_rates
        return state

    def consumer_decision_phase(self, state: SimulationState) -> SimulationState:
        """Process all consumer decisions."""
        # For round 1, use the initial consumers
        # For subsequent rounds, generate new consumers based on amortization flow
        if state["current_round"] > 1:
            state["consumers"] = self._generate_consumers_for_round(state)
        
        # Build portfolio history from market log for consumer utility calculations
        portfolio_history = self._build_portfolio_history(state)
        
        # Calculate bank lending capacities (10x equity - current portfolio)
        bank_capacities = self._calculate_bank_capacities(state)
        
        # Prepare choice configuration
        choice_config = {
            "logit_temperature": self.config["consumer_choice_params"]["logit_temperature"],
            "utility_noise_std": self.config["consumer_choice_params"]["utility_noise_std"],
            "reservation_utility": self.config["behavior_params"]["reservation_utility"]
        }
        
        allocations = self.consumer_engine.allocate_consumers(
            state["consumers"],
            state["market_rates"],
            state["banks"],
            state["active_bank_ids"],
            self.config["behavior_params"]["reservation_utility"],
            portfolio_history,
            bank_capacities,
            choice_config,
        )

        state["consumer_allocations"] = allocations
        return state

    def calculate_financials(self, state: SimulationState) -> SimulationState:
        """Update portfolios and calculate P&L for all banks."""
        # Store start-of-round portfolio balances before amortization
        start_portfolio_balances = {}
        for bank_id in state["banks"]["id"]:
            bank_portfolio = state["portfolio_ledger"][
                (state["portfolio_ledger"]["bank_id"] == bank_id) &
                (state["portfolio_ledger"]["is_active"] == True)
            ]
            start_portfolio_balances[bank_id] = bank_portfolio["principal_outstanding"].sum()
        
        state["start_portfolio_balances"] = start_portfolio_balances
        
        # Amortize existing portfolio
        state["portfolio_ledger"] = self.financial_calc.amortize_portfolio(
            state["portfolio_ledger"],
            state["current_round"],
            self.config["simulation_params"]["amortization_years"],
        )

        # Create new loans from consumer allocations
        new_loans = self._create_new_loans(state)
        if not new_loans.empty:
            state["portfolio_ledger"] = pd.concat(
                [state["portfolio_ledger"], new_loans], ignore_index=True
            )

        # Calculate P&L for each bank
        new_financials = {}
        for bank_id in state["banks"]["id"]:
            # Calculate new loan volume for this bank
            new_loan_volume = 0
            for consumer_id, allocated_bank_id in state["consumer_allocations"].items():
                if allocated_bank_id == bank_id:
                    consumer = state["consumers"][
                        state["consumers"]["id"] == consumer_id
                    ].iloc[0]
                    new_loan_volume += consumer["loan_size"]

            financials = self.financial_calc.calculate_bank_pnl(
                bank_id,
                state["portfolio_ledger"],
                state["market_rates"].get(bank_id, 0),
                state["consumer_allocations"],
                state["banks"],
                state["bank_financials"][bank_id].equity,
                state["current_round"],
                new_loan_volume,
                state["market_history"],
            )
            new_financials[bank_id] = financials

        state["bank_financials"] = new_financials
        return state

    def _create_new_loans(self, state: SimulationState) -> pd.DataFrame:
        """Create new loan records from consumer allocations."""
        new_loans = []

        for consumer_id, bank_id in state["consumer_allocations"].items():
            if bank_id is None:
                continue

            consumer = state["consumers"][state["consumers"]["id"] == consumer_id].iloc[
                0
            ]

            new_loans.append(
                {
                    "loan_id": f"L{datetime.now().timestamp():.0f}{len(new_loans):04d}",
                    "consumer_id": consumer_id,
                    "bank_id": bank_id,
                    "principal_start": consumer["loan_size"],
                    "interest_rate_bps": state["market_rates"][bank_id],
                    "round_added": state["current_round"],
                    "principal_outstanding": consumer["loan_size"],
                    "is_active": True,
                }
            )

        return pd.DataFrame(new_loans)

    def record_round_results(self, state: SimulationState) -> SimulationState:
        """Record round results for output."""
        # Update active bank list for next round based on current portfolio balances
        # This ensures banks with $0.0 balance after this round don't participate in next round
        active_banks_next_round = []
        for bank_id in state["banks"]["id"]:
            # Check if bank is bankrupt
            if state["bank_financials"][bank_id].is_bankrupt:
                continue
                
            # Check if bank has zero portfolio balance (cannot originate loans)
            bank_portfolio = state["portfolio_ledger"][
                (state["portfolio_ledger"]["bank_id"] == bank_id) &
                (state["portfolio_ledger"]["is_active"] == True)
            ]
            portfolio_balance = bank_portfolio["principal_outstanding"].sum()
            
            if portfolio_balance <= 0:
                logger.info(f"Bank {bank_id} will be excluded from next round: zero portfolio balance")
                continue
                
            active_banks_next_round.append(bank_id)
        
        # Store for next round (but don't update current round's active list)
        state["active_bank_ids_next_round"] = active_banks_next_round
        
        # Create market snapshot
        snapshot = MarketSnapshot(
            round=state["current_round"],
            offered_rates=state["market_rates"].copy(),
            new_volumes={
                bank_id: sum(
                    state["consumers"][state["consumers"]["id"] == c_id][
                        "loan_size"
                    ].values[0]
                    for c_id, b_id in state["consumer_allocations"].items()
                    if b_id == bank_id
                )
                for bank_id in state["banks"]["id"]
            },
            new_counts={
                bank_id: sum(
                    1
                    for _, b_id in state["consumer_allocations"].items()
                    if b_id == bank_id
                )
                for bank_id in state["banks"]["id"]
            },
            profits={
                bank_id: fin.profit for bank_id, fin in state["bank_financials"].items()
            },
            equities={
                bank_id: fin.equity for bank_id, fin in state["bank_financials"].items()
            },
            bankruptcies=[
                bank_id
                for bank_id, fin in state["bank_financials"].items()
                if fin.is_bankrupt
            ],
        )

        state["market_history"].append(snapshot)

        # Create enhanced market log entry with detailed loan and rate information
        market_log_entries = []
        for bank_id, fin in state["bank_financials"].items():
            bank_strategy = state["banks"][state["banks"]["id"] == bank_id][
                "strategy"
            ].values[0]
            
            # Calculate portfolio metrics at end of round
            end_portfolio = state["portfolio_ledger"][
                (state["portfolio_ledger"]["bank_id"] == bank_id) &
                (state["portfolio_ledger"]["is_active"] == True)
            ]
            
            # Get start-of-round portfolio (before this round's amortization and new loans)
            # This should be all active loans at the start of the round
            start_portfolio = state["portfolio_ledger"][
                (state["portfolio_ledger"]["bank_id"] == bank_id) &
                (state["portfolio_ledger"]["is_active"] == True) &
                (state["portfolio_ledger"]["round_added"] < state["current_round"])
            ]
            
            # Calculate rates
            end_loan_count = len(end_portfolio)
            start_loan_count = len(start_portfolio)
            
            # Calculate weighted average rates
            if end_loan_count > 0 and end_portfolio["principal_outstanding"].sum() > 0:
                end_avg_rate = (end_portfolio["principal_outstanding"] * end_portfolio["interest_rate_bps"]).sum() / end_portfolio["principal_outstanding"].sum()
            else:
                end_avg_rate = 0
                
            if start_loan_count > 0 and start_portfolio["principal_outstanding"].sum() > 0:
                start_avg_rate = (start_portfolio["principal_outstanding"] * start_portfolio["interest_rate_bps"]).sum() / start_portfolio["principal_outstanding"].sum()
            else:
                start_avg_rate = 500  # Use initial rate for round 1
            
            # Get initial loan count (round 0 loans)
            initial_portfolio = state["portfolio_ledger"][
                (state["portfolio_ledger"]["bank_id"] == bank_id) &
                (state["portfolio_ledger"]["round_added"] == 0)
            ]
            initial_loan_count = len(initial_portfolio)

            # Get the bank's decision score from this round
            bank_decision = state["bank_decisions"].get(bank_id, {})
            decision_score = bank_decision.get("previous_decision_score", None)
            
            market_log_entries.append(
                {
                    "bank_id": bank_id,
                    "round": state["current_round"],
                    "strategy": bank_strategy,
                    "offered_rate": state["market_rates"].get(bank_id, 0),
                    "new_loan_volume": snapshot.new_volumes[bank_id],
                    "new_loan_count": snapshot.new_counts[bank_id],
                    "profit": fin.profit,
                    "equity": fin.equity,
                    "ROE": fin.roe,
                    "bankrupt_flag": fin.is_bankrupt,
                    "previous_decision_score": decision_score,  # Self-evaluation score
                    # Enhanced portfolio tracking
                    "initial_loan_count": initial_loan_count,
                    "start_loan_count": start_loan_count,
                    "end_loan_count": end_loan_count,
                    "start_avg_rate_bps": start_avg_rate,
                    "end_avg_rate_bps": end_avg_rate,
                    "portfolio_balance_start": start_portfolio["principal_outstanding"].sum(),
                    "portfolio_balance_end": end_portfolio["principal_outstanding"].sum(),
                    "loans_added": snapshot.new_counts[bank_id],
                    "loans_amortized": max(0, start_loan_count + snapshot.new_counts[bank_id] - end_loan_count),
                }
            )

        state["market_log"].extend(market_log_entries)

        return state

    def check_continuation(self, state: SimulationState) -> str:
        """Check if simulation should continue or end."""
        logger.info(
            f"Checking continuation: Round {state['current_round']} of {self.config['simulation_params']['rounds']}"
        )

        # End if we've completed all rounds
        if state["current_round"] >= self.config["simulation_params"]["rounds"]:
            logger.info("Simulation complete: All rounds finished")
            return "end"

        # End if all banks are bankrupt
        if len(state["active_bank_ids"]) == 0:
            logger.warning("All banks are bankrupt! Ending simulation.")
            return "end"

        logger.info("Continuing to next round")
        return "continue"

    async def generate_summary(self, state: SimulationState) -> SimulationState:
        """Generate AI-powered summary of simulation results."""
        summary = await self.summary_agent.generate_summary(
            state["market_log"], state["portfolio_ledger"], state["banks"], self.config
        )

        # Save outputs
        self._save_outputs(state, summary)
        
        # Store summary content in state for lessons extraction
        state["summary_content"] = summary

        return state
    
    async def extract_lessons(self, state: SimulationState) -> SimulationState:
        """Extract lessons learned after all iterations are complete."""
        logger.info("Extracting lessons learned from simulation...")
        
        # Skip if memory is disabled
        if self.config.get("disable_memory", False):
            logger.info("Memory disabled, skipping lessons extraction")
            return state
            
        # Extract lessons using the AI agent
        initial_banks = []
        for bank_config in state["initial_bank_configs"]:
            initial_banks.append(Bank(
                id=bank_config["name"],
                strategy=BankStrategy(bank_config["strategy"]),
                image_score=bank_config["image_score"],
                execution_speed=bank_config["execution_speed"],
                cost_of_funds_bps=bank_config["cost_of_funds_bps"],
                operating_cost_per_loan=bank_config["operating_cost_per_loan"],
                initial_equity=bank_config["equity"],
                initial_portfolio_balance=bank_config["initial_portfolio_balance"]
            ))
        
        lessons, patterns, lessons_md = await self.lessons_agent.extract_lessons(
            state,
            state["summary_content"],
            initial_banks,
            self.config
        )
        
        # Save lessons to file (only if output directory exists)
        if self.output_dir:
            filename = f"{self.file_prefix}lessons_learned.md" if self.file_prefix else "lessons_learned.md"
            lessons_path = os.path.join(self.output_dir, filename)
            with open(lessons_path, "w", encoding="utf-8") as f:
                f.write(lessons_md)
            logger.info(f"Saved {lessons_path}")
        
        # Store in state
        state["lessons_content"] = lessons_md
        
        logger.info(f"Extracted {len(lessons)} lessons and {len(patterns)} patterns")
        return state

    def _save_outputs(self, state: SimulationState, summary: str):
        """Save all simulation outputs."""
        if not self.output_dir:
            raise ValueError("No output directory available for saving files")
            
        # Save market log
        market_log_df = pd.DataFrame(state["market_log"])
        filename = f"{self.file_prefix}market_log.parquet" if self.file_prefix else "market_log.parquet"
        market_log_path = os.path.join(self.output_dir, filename)
        market_log_df.to_parquet(market_log_path, index=False)
        logger.info(f"Saved {market_log_path}")
        
        # Also save market log as Excel
        try:
            filename = f"{self.file_prefix}market_log.xlsx" if self.file_prefix else "market_log.xlsx"
            excel_path = os.path.join(self.output_dir, filename)
            market_log_df.to_excel(excel_path, index=False)
            logger.info(f"Saved {excel_path}")
        except ImportError:
            logger.warning("Could not save Excel file - openpyxl not installed. Run: pip install openpyxl")

        # Save portfolio ledger
        filename = f"{self.file_prefix}portfolio_ledger.parquet" if self.file_prefix else "portfolio_ledger.parquet"
        portfolio_path = os.path.join(self.output_dir, filename)
        state["portfolio_ledger"].to_parquet(portfolio_path, index=False)
        logger.info(f"Saved {portfolio_path}")

        # Save summary
        filename = f"{self.file_prefix}summary.md" if self.file_prefix else "summary.md"
        summary_path = os.path.join(self.output_dir, filename)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary)
        logger.info(f"Saved {summary_path}")
        
        # Save detailed bank decision logs
        if hasattr(self.bank_agent, 'format_decision_logs_markdown'):
            decision_logs_md = self.bank_agent.format_decision_logs_markdown()
            filename = f"{self.file_prefix}bank_decision_logs.md" if self.file_prefix else "bank_decision_logs.md"
            decision_logs_path = os.path.join(self.output_dir, filename)
            with open(decision_logs_path, "w", encoding="utf-8") as f:
                f.write(decision_logs_md)
            logger.info(f"Saved {decision_logs_path}")

    async def run(self):
        """Run the complete simulation."""
        logger.info("Starting loan market simulation...")
        initial_state = {
            "current_round": 0,
            "consumers": pd.DataFrame(),
            "banks": pd.DataFrame(),
            "market_history": [],
            "active_bank_ids": [],
            "bank_decisions": {},
            "market_rates": {},
            "portfolio_ledger": pd.DataFrame(),
            "bank_financials": {},
            "consumer_allocations": {},
            "round_summary": None,
            "market_log": [],
            "start_portfolio_balances": {},
            "initial_bank_configs": None,
            "summary_content": None,
            "lessons_content": None,
        }

        # Configure with recursion limit
        config = {"recursion_limit": 250}
        final_state = await self.graph.ainvoke(initial_state, config=config)
        logger.info("Simulation completed successfully!")
        return final_state
