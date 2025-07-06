# Loan Market Simulation

A sophisticated loan market simulation using LangGraph and AI agents to model competitive dynamics between banks, with two-tier learning and adaptive market design capabilities.

## Overview

This simulation models 10 banks competing for loans from 100 consumers over multiple rounds. Each bank is controlled by an AI agent that makes strategic pricing decisions based on market conditions, competitive intelligence, and financial constraints. The system supports both single simulations and meta-simulations that test different market configurations to discover optimal market design principles.

## Features

- **AI-Powered Bank Agents**: Each bank uses an LLM to make strategic rate decisions
- **Heterogeneous Banks**: Varying sizes ($50M-$500M portfolios), strategies, and cost structures
- **Consumer Choice Model**: Utility-based decisions considering rates, bank image, and service speed
- **Dynamic Competition**: Banks adapt strategies based on market conditions and competitor behavior
- **Two-Tier Learning System**: 
  - Micro-lessons: Insights from individual simulation runs
  - Macro-lessons: Market design principles from testing different configurations
- **Meta-Simulation Mode**: Run multiple "megaruns" with adaptive bank configurations to test hypotheses
- **Long-Term Memory**: Stores lessons learned across simulations for future reference
- **Comprehensive Analytics**: Detailed logging and output datasets for analysis

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set API Key** (required):
   ```bash
   export OPENAI_API_KEY='your-api-key'
   ```

3. **Run Simulation**:
   ```bash
   # Quick test mode (3 rounds, faster model)
   python run_sim.py --test-mode
   
   # Full single simulation (10 rounds)
   python run_sim.py
   
   # Meta-simulation with 3 megaruns
   python run_sim.py --meta-mode --megaruns 3
   
   # Custom configuration
   python run_sim.py --rounds 5 --seed 42 --no-memory
   ```

## Project Structure

```
├── config/                          # Configuration files
│   ├── config.yaml                 # Core simulation settings
│   └── initialise_banks.yaml       # Bank parameters (separated for meta-sim)
├── agents/                          # AI agent implementations
│   ├── bank_agent.py               # Bank decision AI
│   ├── summary_agent.py            # Market analysis AI
│   ├── lessons_agent.py            # Micro-lessons extraction
│   ├── megarun_lessons_agent.py    # Macro-lessons extraction
│   ├── bank_config_agent.py        # Adaptive configuration AI
│   └── synthesis_agent.py          # Cross-megarun synthesis AI
├── src/                             # Core simulation code
│   ├── simulation.py               # Main LangGraph orchestrator
│   ├── meta_simulation.py          # Meta-simulation orchestrator
│   ├── models.py                   # Data structures
│   ├── consumer_logic.py           # Consumer utility model
│   ├── financial_calculator.py     # P&L calculations
│   └── memory_store.py             # Long-term memory database
├── memory/                          # Long-term storage (generated)
│   └── lessons.db                  # SQLite database for lessons
├── data/                            # Output files (organized by timestamp)
│   └── YYYYMMDD_HHMMSS_sim/         # Single simulation outputs
│       ├── market_log.parquet       # Bank performance data
│       ├── market_log.xlsx          # Excel version
│       ├── portfolio_ledger.parquet # Loan-level details
│       ├── summary.md               # Single-run analysis
│       └── lessons_learned.md       # Micro-lessons from run
│   └── YYYYMMDD_HHMMSS_meta_sim/    # Meta-simulation outputs
│       ├── megarun_1_market_log.*   # Megarun 1 simulation data
│       ├── megarun_1_portfolio_ledger.parquet # Megarun 1 loans
│       ├── megarun_1_summary.md     # Megarun 1 analysis
│       ├── megarun_1_lessons_learned.md # Megarun 1 micro-lessons
│       ├── megarun_1_report.md      # Megarun 1 macro-lessons
│       ├── megarun_1_config.yaml    # Configuration used
│       ├── megarun_1_banks_config.yaml # Bank parameters
│       ├── [... similar files for each megarun ...]
│       └── meta_simulation_final_report.md # Cross-megarun synthesis
├── docs/                            # Documentation
├── tests/                           # Test scripts
├── scripts/                         # Setup utilities
└── run_sim.py                      # Command-line interface
```

## Outputs

All simulation outputs are organized in timestamped directories within the `data/` folder. Each run creates a new directory with the format `YYYYMMDD_HHMMSS_[type]`, ensuring no outputs are overwritten.

### Single Simulation Mode
Creates a directory like `data/20240115_143022_sim/` containing:

1. **market_log.parquet/xlsx**: Round-by-round bank performance metrics
2. **portfolio_ledger.parquet**: Complete loan-level transaction history
3. **summary.md**: AI-generated strategic analysis
4. **lessons_learned.md**: Key insights and patterns identified

### Meta-Simulation Mode
Creates a directory like `data/20240115_143022_meta_sim/` containing all files from all megaruns:

1. **megarun_N_market_log.parquet/xlsx**: Bank performance data for each megarun
2. **megarun_N_portfolio_ledger.parquet**: Loan data for each megarun
3. **megarun_N_summary.md**: AI analysis for each megarun
4. **megarun_N_lessons_learned.md**: Micro-lessons for each megarun
5. **megarun_N_report.md**: Macro-lessons analysis for each megarun
6. **megarun_N_config.yaml**: Configuration used for each megarun
7. **megarun_N_banks_config.yaml**: Bank parameters for each megarun
8. **meta_simulation_final_report.md**: Synthesis of insights across all megaruns

The memory database (`memory/lessons.db`) persists across all runs for long-term learning.

## Configuration

### Core Settings
Edit `config/config.yaml` to customize:
- Simulation parameters (rounds, consumers)
- AI agent model selection
- Random seed for reproducibility

### Bank Configuration
Edit `config/initialise_banks.yaml` to customize:
- Individual bank parameters (size, strategy, costs)
- Bank characteristics (image score, execution speed)
- Initial portfolio states

## Command-Line Options

```bash
python run_sim.py [OPTIONS]

Options:
  --config PATH         Path to config file (default: config/config.yaml)
  --banks-config PATH   Path to banks config (default: config/initialise_banks.yaml)
  --rounds N            Override number of rounds
  --seed N              Set random seed
  --test-mode           Quick test (3 rounds, faster model)
  --meta-mode           Run meta-simulation with multiple megaruns
  --megaruns N          Number of megaruns for meta-simulation (default: 3)
  --no-memory           Disable lessons extraction
  --verbose             Enable detailed logging
```

## Bank Profiles

The simulation includes diverse bank types:
- **Large Banks** (e.g., MegaBank): $500M portfolio, low funding costs, strong brand
- **FinTechs**: Small, efficient operations, high execution speed
- **Regional Banks**: Medium size, local reputation, balanced approach
- **Growth Banks**: Aggressive pricing to gain market share

See `config/initialise_banks.yaml` for full bank specifications.

## Meta-Simulation Feature

The meta-simulation mode runs multiple "megaruns" to test different market configurations and extract macro-level insights about optimal market design. Each megarun:

1. **Tests a Hypothesis**: Based on historical lessons, the AI generates hypotheses about market design
2. **Modifies Bank Configurations**: Adjusts parameters to test the hypothesis (e.g., higher equity, different strategy mix)
3. **Runs Full Simulation**: Executes a complete simulation with the modified configuration
4. **Extracts Macro-Lessons**: Identifies insights about how configuration affects market outcomes
5. **Validates Hypotheses**: Determines if the hypothesis was confirmed, rejected, or inconclusive

After all megaruns complete, a synthesis agent analyzes patterns across all runs to generate final recommendations for market designers.

### Example Meta-Simulation Hypotheses:
- "Higher average equity (50% increase) leads to more stable markets with fewer bankruptcies"
- "More growth-oriented banks (80% Growth strategy) creates winner-take-all dynamics"
- "Balanced image scores (0.6-0.8 range) optimize market competition vs stability"

## Learning System

The simulation implements a two-tier learning system:

### Micro-Lessons (Single Simulation)
- Extracted after each simulation run
- Focus on bank strategies, market dynamics, and competitive patterns
- Stored in `data/lessons_learned.md`

### Macro-Lessons (Meta-Simulation)
- Extracted after each megarun
- Focus on market configuration effects and design principles
- Stored in `memory/lessons.db` for long-term reference
- Synthesized into final recommendations in `data/meta_simulation_final_report.md`

The learning system enables the simulation to build knowledge over time and test increasingly sophisticated hypotheses about market design.