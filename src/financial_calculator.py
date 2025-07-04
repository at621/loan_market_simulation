"""Financial calculations for P&L, portfolio management, and bank metrics."""

import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging

from src.models import BankFinancials

logger = logging.getLogger(__name__)


class FinancialCalculator:
    """Handles all financial calculations for the simulation."""
    
    def amortize_portfolio(self, 
                          portfolio: pd.DataFrame, 
                          current_round: int,
                          amortization_years: int) -> pd.DataFrame:
        """
        Amortize the loan portfolio for the current round.
        
        Each loan amortizes by 1/amortization_years of its original principal per round.
        Loans become inactive after amortization_years rounds.
        """
        portfolio = portfolio.copy()
        
        # Only process active loans
        active_mask = portfolio['is_active'] == True
        
        if active_mask.sum() == 0:
            return portfolio
        
        # Calculate amortization amount (straight-line)
        portfolio.loc[active_mask, 'amortization'] = (
            portfolio.loc[active_mask, 'principal_start'] / amortization_years
        )
        
        # Reduce principal outstanding
        portfolio.loc[active_mask, 'principal_outstanding'] = (
            portfolio.loc[active_mask, 'principal_outstanding'] - 
            portfolio.loc[active_mask, 'amortization']
        )
        
        # Mark loans as inactive if fully amortized
        rounds_since_origination = current_round - portfolio.loc[active_mask, 'round_added']
        fully_amortized = rounds_since_origination >= amortization_years
        
        portfolio.loc[active_mask & fully_amortized, 'is_active'] = False
        portfolio.loc[active_mask & fully_amortized, 'principal_outstanding'] = 0
        
        # Clean up temporary column
        if 'amortization' in portfolio.columns:
            portfolio = portfolio.drop('amortization', axis=1)
        
        logger.info(f"Amortized {active_mask.sum()} active loans")
        
        return portfolio
    
    def calculate_bank_pnl(self,
                          bank_id: str,
                          portfolio: pd.DataFrame,
                          offered_rate: int,
                          consumer_allocations: Dict[str, Optional[str]],
                          banks: pd.DataFrame,
                          previous_equity: float,
                          current_round: int,
                          new_loan_volume: float = 0) -> BankFinancials:
        """
        Calculate P&L for a bank for the current round.
        
        Following the spec:
        1. Gross Interest Income = old book income + new book income
        2. Interest Expense = total funded balance × cost of funds
        3. Net Interest Income = Gross Income - Interest Expense
        4. Operating Cost = cost per loan × number of new loans
        5. Profit = NII - OpEx
        6. Equity = Previous Equity + Profit
        7. ROE = Profit / Previous Equity
        """
        bank_info = banks[banks['id'] == bank_id].iloc[0]
        
        # Get bank's portfolio
        bank_portfolio = portfolio[
            (portfolio['bank_id'] == bank_id) & 
            (portfolio['is_active'] == True)
        ]
        
        # 1. Calculate old book income (from existing loans)
        old_book_income = 0
        if not bank_portfolio.empty:
            # Income = principal × rate for each loan
            old_book_income = (
                bank_portfolio['principal_outstanding'] * 
                bank_portfolio['interest_rate_bps'] / 10000
            ).sum()
        
        # 2. Calculate new book metrics
        new_loan_ids = [
            c_id for c_id, b_id in consumer_allocations.items() 
            if b_id == bank_id
        ]
        new_loan_count = len(new_loan_ids)
        
        # new_loan_volume is now passed as parameter
        
        new_book_income = new_loan_volume * offered_rate / 10000
        
        # 3. Total gross interest income
        gross_interest_income = old_book_income + new_book_income
        
        # 4. Calculate interest expense
        portfolio_balance = bank_portfolio['principal_outstanding'].sum()
        total_funded_balance = portfolio_balance + new_loan_volume
        interest_expense = total_funded_balance * bank_info['cost_of_funds_bps'] / 10000
        
        # 5. Net interest income
        net_interest_income = gross_interest_income - interest_expense
        
        # 6. Operating costs
        operating_cost = new_loan_count * bank_info['operating_cost_per_loan']
        
        # 7. Profit
        profit = net_interest_income - operating_cost
        
        # 8. Update equity
        current_equity = previous_equity + profit
        
        # 9. Calculate ROE
        if previous_equity > 0:
            roe = profit / previous_equity
        else:
            roe = -np.inf if profit < 0 else 0
        
        # 10. Check bankruptcy
        is_bankrupt = current_equity <= 0
        
        # Log details for debugging
        logger.debug(f"""
        Bank {bank_id} P&L:
        - Old book income: ${old_book_income:,.2f}
        - New loans: {new_loan_count} (${new_loan_volume:,.0f})
        - New book income: ${new_book_income:,.2f}
        - Gross income: ${gross_interest_income:,.2f}
        - Interest expense: ${interest_expense:,.2f}
        - NII: ${net_interest_income:,.2f}
        - OpEx: ${operating_cost:,.2f}
        - Profit: ${profit:,.2f}
        - Equity: ${previous_equity:,.0f} -> ${current_equity:,.0f}
        - ROE: {roe:.1%}
        """)
        
        return BankFinancials(
            bank_id=bank_id,
            round=current_round,
            equity=current_equity,
            portfolio_balance=portfolio_balance,
            new_loan_volume=new_loan_volume,
            new_loan_count=new_loan_count,
            gross_interest_income=gross_interest_income,
            interest_expense=interest_expense,
            net_interest_income=net_interest_income,
            operating_cost=operating_cost,
            profit=profit,
            roe=roe,
            is_bankrupt=is_bankrupt
        )
    
    def calculate_portfolio_metrics(self, portfolio: pd.DataFrame) -> Dict:
        """Calculate portfolio-level metrics."""
        active_portfolio = portfolio[portfolio['is_active'] == True]
        
        metrics = {
            'total_loans': len(portfolio),
            'active_loans': len(active_portfolio),
            'total_principal_outstanding': active_portfolio['principal_outstanding'].sum(),
            'average_rate': active_portfolio['interest_rate_bps'].mean() if len(active_portfolio) > 0 else 0,
            'weighted_average_rate': (
                (active_portfolio['principal_outstanding'] * active_portfolio['interest_rate_bps']).sum() /
                active_portfolio['principal_outstanding'].sum()
            ) if active_portfolio['principal_outstanding'].sum() > 0 else 0
        }
        
        # Portfolio by bank
        bank_portfolios = {}
        for bank_id in portfolio['bank_id'].unique():
            bank_active = active_portfolio[active_portfolio['bank_id'] == bank_id]
            bank_portfolios[bank_id] = {
                'active_loans': len(bank_active),
                'principal_outstanding': bank_active['principal_outstanding'].sum(),
                'average_rate': bank_active['interest_rate_bps'].mean() if len(bank_active) > 0 else 0
            }
        
        metrics['by_bank'] = bank_portfolios
        
        return metrics