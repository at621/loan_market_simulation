# Loan-Market Simulation Project

## Overview
This project implements a loan-market simulation where 10 banks compete for 100 heterogeneous consumers' loan business over 10 annual rounds. The complete specification is in `simulation_specs.md`.

## Project Structure
```
/mnt/c/projects/vs_code_claude_test/
├── config/                  # Configuration files
│   └── config.yaml         # Simulation parameters & bank setups
├── agents/                  # AI agent implementations  
│   ├── bank_agent.py       # Bank decision AI
│   └── summary_agent.py    # Analysis AI
├── data/                    # Output files (generated)
│   ├── market_log.parquet  # Bank KPIs by round
│   ├── market_log.xlsx     # Excel version
│   ├── portfolio_ledger.parquet # Loan-level data
│   └── summary.md          # AI analysis
├── tests/                   # Test files
│   └── verify_implementation.py
├── src/                    # Core source code
│   ├── simulation.py      # Main LangGraph orchestrator
│   ├── models.py          # Data structures
│   ├── consumer_logic.py  # Consumer decisions
│   └── financial_calculator.py # P&L calculations
├── docs/                   # Documentation
│   ├── simulation_specs.md # Full specifications
│   └── PROJECT_STRUCTURE.md # Architecture
├── scripts/               # Setup and utility scripts
│   └── setup.py
├── run_sim.py            # CLI runner
└── requirements.txt      # Dependencies
```

## Key Components

### 1. Core Entities
- **Consumers (100)**: Have rate sensitivity, image weight, speed weight, and loan size
- **Banks (10)**: Have strategy (Grow/Maintain), image score, execution speed, costs, and equity
- **Portfolio Ledger**: Tracks all loans with principal, rates, and amortization status

### 2. Simulation Flow
1. Initialize entities and pre-populate portfolio
2. For each round (1-10):
   - Banks set interest rates based on strategy
   - Consumers choose banks based on utility function
   - Update portfolio with new loans and amortization
   - Calculate P&L, equity, and check for bankruptcy
   - Record results
3. Generate summary report

### 3. Key Behaviors
- **Consumer Choice**: Utility = weighted sum of rate score, image score, and execution speed
- **Bank Strategies**:
  - Grow: Undercut average rate if profitable
  - Maintain: Follow median rate with random walk
- **Loan Amortization**: 5-year straight-line (20% per year)

## Implementation Guidelines

### When implementing:
1. Use vectorized operations for consumer decisions (all 100 at once)
2. Process banks in parallel where possible
3. Maintain efficiency with lightweight shared state
4. Include safeguards (10 round limit, 1000 row loan table limit)

### Testing Commands
```bash
# Run the simulation
python run_sim.py

# Run tests (if implemented)
pytest tests/

# Check code quality
python -m black .
python -m flake8 .
```

## Output Files
- `market_log.parquet`: Round-by-round bank performance metrics
- `portfolio_ledger.parquet`: Complete loan-level transaction history
- `summary.md`: Narrative analysis of winning strategies and market dynamics

## Configuration
Edit `config.yaml` to adjust:
- Number of rounds
- Consumer/bank parameters
- Behavioral parameters (reservation utility, undercut amounts, etc.)
- Random seed for reproducibility

## Implementation Architecture

### LangGraph with AI Agents
The simulation uses LangGraph with the Send API for parallel bank decisions:
- Each bank is controlled by an AI agent (LLM)
- Banks make decisions simultaneously based on market history and their own financial position
- All banks have access to complete market information and competitor strategies
- Each bank optimizes for its own long-term profitability given its constraints

### Key Design Features
1. **Parallel Decision Making**: Using Send API, all active banks make rate decisions simultaneously
2. **Full Information Game**: Banks see complete history and know competitor strategies (Grow/Maintain)
3. **Individual Optimization**: Each bank maximizes its own cumulative profit based on its unique situation
4. **Dynamic Adaptation**: AI agents can adapt strategies based on market conditions

## Testing Requirements

### Before considering the implementation complete:
1. **Unit Tests**: Test individual components (consumer utility, P&L calculations, amortization)
2. **Integration Test**: Run a complete 10-round simulation
3. **Validation Checks**:
   - Verify portfolio ledger consistency
   - Confirm P&L calculations match expected formulas
   - Check bankruptcy mechanics work correctly
   - Validate consumer decision logic
4. **Output Verification**:
   - Ensure `market_log.parquet` contains all required fields
   - Verify `portfolio_ledger.parquet` tracks loans correctly
   - Confirm `summary.md` generates meaningful insights

### Setup Instructions

1. **Install Dependencies**:
```bash
# Install required packages
python3 setup.py

# Or manually:
pip install -r requirements.txt
```

2. **Set API Key**:
```bash
# Set your OpenAI API key
export OPENAI_API_KEY='your-api-key-here'
```

3. **Verify Implementation**:
```bash
# Run verification tests
python3 verify_implementation.py
```

### Test Scenarios to Run

```bash
# Basic simulation test (3 rounds, faster model)
python3 run_sim.py --test-mode

# Full simulation (10 rounds)
python3 run_sim.py

# Custom parameters
python3 run_sim.py --rounds 5 --seed 42

# Verbose logging for debugging
python3 run_sim.py --test-mode --verbose
```

### Expected Behaviors to Verify
1. Banks with low equity become more conservative
2. Grow strategy banks undercut when profitable
3. Consumer choices follow utility maximization
4. Loans amortize correctly over 5 rounds
5. Market reaches some form of equilibrium or competitive dynamics