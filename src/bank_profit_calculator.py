"""
Simple profit calculator function for bank agents.
"""

from typing import Dict, List, Tuple
from src.consumer_logic import ConsumerDecisionEngine


def calculate_expected_profits(
    bank_id: str,
    bank_info: Dict,
    market_rates: Dict[str, int],
    consumers: List,
    test_rates: List[int],
    bank_image_scores: Dict[str, float],
    bank_execution_speeds: Dict[str, float],
    bank_capacities: Dict[str, float]
) -> List[Dict]:
    """
    Calculate expected profits for different rate scenarios, assuming other banks keep their rates constant.
    
    Args:
        bank_id: ID of the bank making the decision
        bank_info: Dictionary with bank's financial information
        market_rates: Current market rates {bank_id: rate_bps}
        consumers: List of consumer objects for this round
        test_rates: List of rates (in bps) to test for this bank
        bank_image_scores: Image scores for all banks
        bank_execution_speeds: Execution speeds for all banks  
        bank_capacities: Available lending capacity for all banks
        
    Returns:
        List of dictionaries with profit projections for each test rate
    """
    consumer_engine = ConsumerDecisionEngine()
    projections = []
    
    # Extract bank financial info
    current_equity = bank_info.get("current_equity", 0)
    cost_of_funds_bps = bank_info.get("cost_of_funds_bps", 300)
    operating_cost_per_loan = bank_info.get("operating_cost_per_loan", 500)
    
    for test_rate in test_rates:
        # Create scenario with our test rate, others keep current rates
        scenario_rates = market_rates.copy()
        scenario_rates[bank_id] = test_rate
        
        # Simulate consumer allocation
        allocations = consumer_engine.allocate_consumers_to_banks(
            consumers=consumers,
            bank_rates=scenario_rates,
            bank_image_scores=bank_image_scores,
            bank_execution_speeds=bank_execution_speeds,
            bank_capacities=bank_capacities
        )
        
        # Calculate results for our bank
        our_loans = [alloc for alloc in allocations if alloc.get("chosen_bank") == bank_id]
        
        new_loans_count = len(our_loans)
        new_loan_volume = sum(consumer.loan_size for consumer in our_loans if hasattr(consumer, 'loan_size'))
        if new_loan_volume == 0 and new_loans_count > 0:
            # Fallback if loan_size not available
            new_loan_volume = new_loans_count * 100_000  # Assume $100k average
        
        # Calculate profit components
        # Revenue = loan volume * interest rate
        annual_revenue = new_loan_volume * (test_rate / 10_000)  # Convert bps to decimal
        
        # Costs = funding cost + operating costs
        funding_cost = new_loan_volume * (cost_of_funds_bps / 10_000)
        operating_costs = new_loans_count * operating_cost_per_loan
        total_costs = funding_cost + operating_costs
        
        # Net profit
        net_profit = annual_revenue - total_costs
        
        # Calculate market share
        total_allocated = len([alloc for alloc in allocations if alloc.get("chosen_bank") is not None])
        market_share = (new_loans_count / max(1, total_allocated)) * 100
        
        # Calculate capacity utilization
        available_capacity = bank_capacities.get(bank_id, 0)
        capacity_utilization = (new_loan_volume / max(1, available_capacity)) * 100 if available_capacity > 0 else 0
        
        # Calculate ROE
        roe = (net_profit / max(1, current_equity)) * 100 if current_equity > 0 else 0
        
        projections.append({
            "test_rate_bps": test_rate,
            "new_loans_count": new_loans_count,
            "new_loan_volume": new_loan_volume,
            "annual_revenue": annual_revenue,
            "funding_cost": funding_cost,
            "operating_costs": operating_costs,
            "total_costs": total_costs,
            "net_profit": net_profit,
            "market_share_pct": market_share,
            "capacity_utilization_pct": capacity_utilization,
            "roe_pct": roe
        })
    
    return projections


def find_optimal_rate(projections: List[Dict]) -> Dict:
    """
    Find the rate scenario that maximizes profit.
    
    Args:
        projections: List of profit projection dictionaries
        
    Returns:
        Dictionary with the optimal rate scenario
    """
    if not projections:
        return {}
    
    return max(projections, key=lambda x: x["net_profit"])


def format_profit_analysis(projections: List[Dict], top_n: int = 3) -> str:
    """
    Format profit projections into a readable string for bank agents.
    
    Args:
        projections: List of profit projection dictionaries
        top_n: Number of top scenarios to show
        
    Returns:
        Formatted string with profit analysis
    """
    if not projections:
        return "No profit projections available."
    
    # Sort by profit (descending)
    sorted_projections = sorted(projections, key=lambda x: x["net_profit"], reverse=True)
    
    lines = ["PROFIT PROJECTIONS (assuming competitors maintain current rates):"]
    lines.append("")
    
    for i, proj in enumerate(sorted_projections[:top_n], 1):
        lines.append(f"  Rate {proj['test_rate_bps']} bps:")
        lines.append(f"    Expected new loans: {proj['new_loans_count']:,}")
        lines.append(f"    Expected volume: ${proj['new_loan_volume']:,.0f}")
        lines.append(f"    Expected profit: ${proj['net_profit']:,.0f}")
        lines.append(f"    Expected market share: {proj['market_share_pct']:.1f}%")
        lines.append(f"    Expected ROE: {proj['roe_pct']:.1f}%")
        lines.append("")
    
    # Show optimal rate
    optimal = find_optimal_rate(projections)
    if optimal:
        lines.append(f"PROFIT-MAXIMIZING RATE: {optimal['test_rate_bps']} bps")
        lines.append(f"  Expected profit: ${optimal['net_profit']:,.0f}")
    
    return "\n".join(lines)


# Example usage function
def example_usage():
    """Example of how to use the profit calculator."""
    
    # Example bank info
    bank_info = {
        "current_equity": 50_000_000,
        "cost_of_funds_bps": 300,
        "operating_cost_per_loan": 500
    }
    
    # Example market rates (other banks)
    market_rates = {
        "B00": 480,
        "B01": 490, 
        "B02": 500,
        # ... other banks
    }
    
    # Example test rates to evaluate for our bank
    test_rates = [450, 475, 500, 525, 550]
    
    # Example bank characteristics (simplified)
    bank_image_scores = {"B00": 0.8, "B01": 0.7, "B02": 0.6}
    bank_execution_speeds = {"B00": 0.9, "B01": 0.8, "B02": 0.7}
    bank_capacities = {"B00": 100_000_000, "B01": 80_000_000, "B02": 60_000_000}
    
    # Note: In real usage, you'd pass actual consumer objects
    consumers = []  # This would be the actual consumer list
    
    # Calculate projections
    projections = calculate_expected_profits(
        bank_id="B00",
        bank_info=bank_info,
        market_rates=market_rates,
        consumers=consumers,
        test_rates=test_rates,
        bank_image_scores=bank_image_scores,
        bank_execution_speeds=bank_execution_speeds,
        bank_capacities=bank_capacities
    )
    
    # Format results
    analysis = format_profit_analysis(projections)
    print(analysis)
    
    # Find optimal rate
    optimal = find_optimal_rate(projections)
    print(f"\nOptimal rate: {optimal['test_rate_bps']} bps")