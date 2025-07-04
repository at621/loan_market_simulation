# Loan Market Simulation - Project Structure

```
loan-market-simulation/
│
├── config/                      # Configuration files
│   └── config.yaml             # Main simulation configuration
│
├── agents/                      # AI agent implementations
│   ├── bank_agent.py           # Bank decision AI agent (requires OpenAI)
│   ├── mock_bank_agent.py      # Mock bank agent for testing
│   ├── summary_agent.py        # Summary generation AI agent
│   └── mock_summary_agent.py   # Mock summary agent
│
├── src/                         # Core source code
│   ├── simulation.py           # Main simulation orchestrator (LangGraph)
│   ├── models.py              # Data models and types
│   ├── consumer_logic.py      # Consumer decision logic
│   └── financial_calculator.py # P&L and portfolio calculations
│
├── data/                        # Output data (created on run)
│   ├── market_log.parquet      # Bank performance by round
│   ├── market_log.xlsx         # Excel version of market log
│   ├── portfolio_ledger.parquet # All loan transactions
│   └── summary.md              # AI-generated analysis
│
├── docs/                        # Documentation
│   ├── simulation_specs.md     # Detailed specifications
│   └── PROJECT_STRUCTURE.md    # This file
│
├── tests/                       # Test files
│   └── verify_implementation.py # Basic verification tests
│
├── scripts/                     # Setup and utility scripts
│   └── setup.py                # Setup script
│
├── run_sim.py                  # Command-line runner
├── requirements.txt            # Python dependencies
├── CLAUDE.md                   # Claude AI context file
└── README.md                   # Project documentation
```

## Module Organization

### Core Simulation (`src/`)
- `simulation.py` - Main LangGraph orchestrator
- `models.py` - TypedDict definitions and data classes
- `consumer_logic.py` - Consumer utility maximization
- `financial_calculator.py` - Portfolio amortization and P&L

### AI Agents (`agents/`)
- `bank_agent.py` - LLM-powered bank decisions
- `summary_agent.py` - LLM-powered analysis
- `mock_*.py` - Non-AI versions for testing

### Configuration (`config/`)
- `config.yaml` - All simulation parameters and individual bank setups

### Data Output (`data/`)
- All simulation outputs saved here
  - Parquet files for efficient data analysis
  - Excel files for easy viewing
  - Markdown summary for insights

### Documentation (`docs/`)
- `simulation_specs.md` - Full technical specification
- `PROJECT_STRUCTURE.md` - Architecture overview

### Tests (`tests/`)
- `verify_implementation.py` - Basic verification tests

### Scripts (`scripts/`)
- `setup.py` - Installation helper

## Import Structure

```python
# Main runner
from src.simulation import LoanMarketSimulation

# In simulation.py
from src.models import SimulationState, Bank, Consumer
from src.consumer_logic import ConsumerDecisionEngine
from src.financial_calculator import FinancialCalculator
from agents.bank_agent import BankAgent

# In agents
from src.models import BankDecision
```