# Loan Market Simulation

A sophisticated loan market simulation using LangGraph and AI agents to model competitive dynamics between banks.

## Overview

This simulation models 10 banks competing for loans from 100 consumers over 10 rounds. Each bank is controlled by an AI agent that makes strategic pricing decisions based on market conditions, competitive intelligence, and financial constraints.

## Features

- **AI-Powered Bank Agents**: Each bank uses an LLM to make strategic rate decisions
- **Heterogeneous Banks**: Varying sizes ($50M-$500M portfolios), strategies, and cost structures
- **Consumer Choice Model**: Utility-based decisions considering rates, bank image, and service speed
- **Dynamic Competition**: Banks adapt strategies based on market conditions and competitor behavior
- **Comprehensive Analytics**: Detailed logging and output datasets for analysis

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set API Key** (optional - uses mock agents if not set):
   ```bash
   export OPENAI_API_KEY='your-api-key'
   ```

3. **Run Simulation**:
   ```bash
   python run_sim.py --test-mode  # Quick 3-round test
   python run_sim.py              # Full 10-round simulation
   ```

## Project Structure

```
├── config/                 # Configuration files
│   └── config.yaml        # Bank parameters & simulation settings
├── agents/                 # AI agent implementations
│   ├── bank_agent.py      # LLM-powered bank decisions
│   └── mock_*.py          # Test versions without API
├── src/                    # Core simulation code
│   ├── simulation.py      # Main LangGraph orchestrator
│   ├── models.py          # Data structures
│   ├── consumer_logic.py  # Consumer utility model
│   └── financial_calculator.py # P&L calculations
├── data/                   # Output files (generated)
│   ├── market_log.*       # Bank performance data
│   └── portfolio_ledger.* # Loan-level details
├── docs/                   # Documentation
├── tests/                  # Test scripts
├── scripts/                # Setup utilities
└── run_sim.py             # Command-line interface
```

## Outputs

The simulation generates three main outputs in the `data/` directory:

1. **market_log.parquet/xlsx**: Round-by-round bank performance metrics
2. **portfolio_ledger.parquet**: Complete loan-level transaction history
3. **summary.md**: AI-generated strategic analysis

## Configuration

Edit `config/config.yaml` to customize:
- Individual bank parameters (size, strategy, costs)
- Consumer behavior parameters
- Simulation settings (rounds, random seed)

## Bank Profiles

The simulation includes diverse bank types:
- **Large Banks** (e.g., MegaBank): $500M portfolio, low funding costs, strong brand
- **FinTechs**: Small, efficient operations, high execution speed
- **Regional Banks**: Medium size, local reputation, balanced approach
- **Growth Banks**: Aggressive pricing to gain market share

See `config/config.yaml` for full bank specifications.