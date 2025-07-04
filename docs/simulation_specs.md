### **Complete Specification – Loan-Market Simulation (v1.0)**

#### 1. Objective

*   Simulate 10 annual iterations (“rounds”) in which 10 banks compete for 100 heterogeneous consumers’ loan business.
*   Track dynamic interest-rate competition, loan volumes, profits, equity, and Return on Equity (ROE).
*   A bank exits (bankrupt) if its equity falls to zero or below.
*   Persist two data artifacts:
    1.  `market_log.parquet` – bank-level KPIs per round.
    2.  `portfolio_ledger.parquet` – cumulative loan-level ledger.
*   Produce `summary.md` that narrates which strategies worked and why.

---

#### 2. Core Entities

**Consumers (100 total)**

*   id
*   `rate_sensitivity` in 0-1 (from Beta distribution)
*   `image_weight` in 0-1 (from Beta distribution, then normalized)
*   `speed_weight` in 0-1 (from Beta distribution, then normalized)
*   `loan_size` (from LogNormal distribution)
*   The three weights sum to 1 and remain static.

**Banks (10 total)**

*   id
*   `strategy` – Grow or Maintain (static attribute)
*   `image_score` in 0-1 (from Uniform distribution)
*   `execution_speed` in 0-1 (from Uniform distribution)
*   `cost_of_funds_bps` (basis-points)
*   `operating_cost_per_loan` (currency)
*   `equity_start` (from config)
*   `portfolio_balance_start` (from config)
*   Banks that hit equity ≤ 0 are marked `bankrupt` and cease to play.

**PortfolioLedger – cumulative loan-level table**

*   `loan_id` – UUID or simple counter
*   `consumer_id`
*   `bank_id`
*   `principal_start` – The original loan amount. Remains constant.
*   `interest_rate_bps` – The rate at which the loan was booked.
*   `round_added` – The iteration when the loan was booked.
*   `principal_outstanding` – Updated each round by amortization.
*   `is_active` – Boolean, becomes `False` when the loan is fully amortized (e.g., after 5 rounds).

Nothing is ever deleted from PortfolioLedger; we only append and update.

---

#### 3. Initialisation and Behavioural Models

**A. Initialisation (Pre-Round 1)**

1.  **Attribute Generation:**
    *   Consumer `rate_sensitivity`, `image_weight`, and `speed_weight` are drawn from a `Beta(a, b)` distribution specified in the config. The weights are then normalized to sum to 1.
    *   Consumer `loan_size` is drawn from a `LogNormal(mean, sigma)` distribution specified in the config.
    *   Bank `image_score` and `execution_speed` are drawn from a `Uniform(0, 1)` distribution.
2.  **Initial Portfolio Generation:**
    *   Before Round 1, the `PortfolioLedger` is pre-populated. For each bank, synthetic loans are created to match its `portfolio_balance_start`.
    *   The number of initial loans per bank is `portfolio_balance_start / loan_size_mean`.
    *   These loans are assigned the bank's `portfolio_rate_start_bps` and are randomly distributed among the 100 consumers. Their `round_added` is 0.

**B. Behavioural Models (Per Round)**

**Consumer Choice**
A consumer calculates a utility score for each non-bankrupt bank.
1.  **Rate Score:** `rate_score = (max_rate - offered_rate) / (max_rate - min_rate)`
    *   Where `max_rate` and `min_rate` are the maximum and minimum rates offered by any bank in the current round. If all rates are equal, `rate_score` is 0.5 for all banks.
2.  **Utility Function:** `Utility = (w_rate × (rate_score ^ (1 + rate_sensitivity))) + (w_image × image_score) + (w_speed × execution_speed)`
3.  **Decision:** Each consumer picks the bank with the highest utility, *if* that utility exceeds the global `reservation_utility` from the config. Otherwise, they do not take a loan this round.

**Bank Heuristics**
1.  **Grow Strategy:**
    *   If last-round profit was positive: Offer a rate equal to `(average competitor rate) - grow_undercut_bps`.
    *   If last-round profit was zero or negative: Revert to the Maintain strategy for this round to curb losses.
2.  **Maintain Strategy:**
    *   Offer a rate equal to `(median competitor rate) + random_walk`.
    *   `random_walk` is a value drawn from a `Normal(0, maintain_walk_stdev_bps)` distribution.

**P&L and Balance-Sheet per bank per round**
This follows a standard financial logic. All calculations are per-bank, per-round.

1.  **Amortisation:** For every active loan on the bank's book, reduce its `principal_outstanding` by `(principal_start / 5)`. A loan becomes inactive after 5 rounds.
2.  **Gross Interest Income:**
    *   `old_book_income` = Σ(`principal_outstanding_at_start_of_round` × `interest_rate_bps`) for all existing loans.
    *   `new_book_income` = `new_loan_volume` × `new_offered_rate_bps`.
    *   `Total Gross Income` = `old_book_income` + `new_book_income`.
3.  **Interest Expense:**
    *   `total_funded_balance` = `portfolio_balance_at_start_of_round` + `new_loan_volume`.
    *   `Total Interest Expense` = `total_funded_balance` × `cost_of_funds_bps`.
4.  **Net Interest Income (NII):** `NII = Total Gross Income - Total Interest Expense`.
5.  **Operating Cost:** `OpEx = operating_cost_per_loan × number_of_new_loans`.
6.  **Profit:** `Profit = NII - OpEx`.
7.  **Equity Update:** `Equity_current = Equity_previous + Profit`.
8.  **ROE Calculation:** `ROE = Profit / Equity_previous`. (If `Equity_previous` ≤ 0, ROE is treated as -∞).
9.  **Bankruptcy Check:** If `Equity_current` ≤ 0, the bank is marked as `bankrupt` and will not participate in subsequent rounds.

---

#### 4. Simulation Flow and Efficiency Guarantees

0.  **Initialisation:** Before the loop starts, run the initialisation logic (3.A) to generate attributes and the starting portfolio ledger.
1.  **BroadcastSnapshot:** Node sends last-round market state and bank equity info to all active (non-bankrupt) banks.
2.  **BankAgent Nodes (Parallel):** Ten `BankAgent` nodes run in parallel. Each active bank applies its heuristic (3.B) to determine its `offered_rate`. Bankrupt banks are skipped.
3.  **MergeRates:** Node collects each agent’s offered rate into a single market-wide structure.
4.  **ConsumerDecision:** Node processes all 100 consumers in one vectorized function call, applying the consumer choice model (3.B) to produce allocations and a batch of new loans.
5.  **ProfitAndBalance:** Node updates the `PortfolioLedger` (amortising old loans, appending new ones) and then computes profit, equity, ROE, and bankruptcy flags for each bank using the P&L model (3.B).
6.  **DataRecorder:** Node writes one compact pandas DataFrame (the `market_log` entry for the round) to disk.
7.  **Loop:** Continues until 10 rounds complete or all banks are bankrupt.
8.  **Summary Node:** After the loop, this node reads both `market_log.parquet` and `portfolio_ledger.parquet` to write `summary.md`.

**Safeguards:** Shared state holds only lightweight primitives. Hard stop at 10 rounds. Loan table is limited to 1000 rows (100 consumers * 10 rounds), keeping memory usage low.

---

#### 5. Outputs and Persistence

*   `market_log.parquet`: `bank_id`, `round`, `strategy`, `offered_rate`, `new_loan_volume`, `new_loan_count`, `profit`, `equity`, `ROE`, `bankrupt_flag`.
*   `portfolio_ledger.parquet`: Cumulative loan-level ledger as described in section 2.
*   `summary.md`: Final report containing ending equity/ROE ranking, commentary on cumulative profit and market share, and "lessons learned" contrasting Grow vs. Maintain strategies.

---

#### 6. Configuration File (`config.yaml`)

The config file is expanded to govern all key parameters for reproducibility and experimentation.

```yaml
seed: 42
simulation_params:
  rounds: 10
  amortization_years: 5

customer_params:
  count: 100
  loan_size_dist:
    mean: 100000
    sigma: 25000 # Std Dev for LogNormal distribution
  attribute_dist:
    # Beta distribution parameters (alpha, beta) for 0-1 scores
    # High alpha/beta (e.g., >2) centers the distribution around 0.5
    # One high, one low skews it. (e.g., a=5, b=2 skews towards 1)
    alpha: 2.0
    beta: 2.0

bank_params:
  count: 10
  strategy_split:
    Grow: 5
    Maintain: 5
  initial_conditions:
    cost_of_funds_bps: 300
    operating_cost_per_loan: 1000
    equity_start: 10000000
    portfolio_balance_start: 100000000
    portfolio_rate_start_bps: 500

behavior_params:
  # Consumer reservation utility: if max utility is below this, no loan is taken
  reservation_utility: 0.35
  # Bank Heuristics
  grow_undercut_bps: 15 # How many bps a Grow bank undercuts the avg rate by
  maintain_walk_stdev_bps: 5 # Std Dev of the random walk for Maintain banks
```

---

#### 7. Deliverables

*   `simulation.py` – LangGraph (or other framework) implementation respecting this spec.
*   `config.yaml` – The editable input file shown above.
*   `run_sim.py` – Command-line runner that loads the config, executes the simulation, and saves all outputs.
*   (Optional) `analysis.ipynb` – Offline exploratory notebook for deeper analysis.