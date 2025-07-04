#!/usr/bin/env python3
"""Basic verification tests for the loan market simulation."""

import sys
import traceback
from pathlib import Path

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        import src.models
        print("✓ models imported")
        
        import src.consumer_logic
        print("✓ consumer_logic imported")
        
        import src.financial_calculator
        print("✓ financial_calculator imported")
        
        import agents.summary_agent
        print("✓ summary_agent imported")
        
        import agents.bank_agent
        print("✓ bank_agent imported")
        
        import src.simulation
        print("✓ simulation imported")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        traceback.print_exc()
        return False

def test_config():
    """Test configuration loading."""
    print("\nTesting config loading...")
    
    try:
        import yaml
        with open('config/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        required_keys = ['seed', 'simulation_params', 'customer_params', 'bank_params']
        for key in required_keys:
            if key not in config:
                print(f"✗ Missing config key: {key}")
                return False
        
        print("✓ Configuration loaded successfully")
        return True
    except Exception as e:
        print(f"✗ Config loading failed: {e}")
        return False

def test_data_models():
    """Test basic data model functionality."""
    print("\nTesting data models...")
    
    try:
        from src.models import Consumer, Bank, BankStrategy, BankDecision
        
        # Test consumer creation
        consumer = Consumer(
            id="C001",
            rate_sensitivity=0.5,
            image_weight=0.3,
            speed_weight=0.3,
            rate_weight=0.4,
            loan_size=100000
        )
        
        utility = consumer.calculate_utility(0.8, 0.7, 0.6)
        print(f"✓ Consumer utility calculation: {utility:.3f}")
        
        # Test bank creation
        bank = Bank(
            id="B01",
            strategy=BankStrategy.GROW,
            image_score=0.8,
            execution_speed=0.7,
            cost_of_funds_bps=300,
            operating_cost_per_loan=1000,
            initial_equity=10000000,
            initial_portfolio_balance=100000000
        )
        print("✓ Bank object created")
        
        # Test bank decision
        decision = BankDecision(
            bank_id="B01",
            rate_bps=450,
            reasoning="Test decision",
            expected_outcome="Gain market share"
        )
        
        if decision.validate():
            print("✓ Bank decision validation passed")
        else:
            print("✗ Bank decision validation failed")
            return False
        
        return True
    except Exception as e:
        print(f"✗ Data model test failed: {e}")
        traceback.print_exc()
        return False

def test_consumer_logic():
    """Test consumer decision logic."""
    print("\nTesting consumer logic...")
    
    try:
        import pandas as pd
        from src.consumer_logic import ConsumerDecisionEngine
        
        # Create test data
        consumers = pd.DataFrame({
            'id': ['C001', 'C002'],
            'rate_sensitivity': [0.5, 0.3],
            'image_weight': [0.3, 0.4],
            'speed_weight': [0.3, 0.3],
            'rate_weight': [0.4, 0.3],
            'loan_size': [100000, 120000]
        })
        
        banks = pd.DataFrame({
            'id': ['B01', 'B02'],
            'image_score': [0.8, 0.6],
            'execution_speed': [0.7, 0.9]
        })
        
        market_rates = {'B01': 400, 'B02': 450}
        active_banks = ['B01', 'B02']
        
        engine = ConsumerDecisionEngine()
        allocations = engine.allocate_consumers(
            consumers, market_rates, banks, active_banks, 0.3
        )
        
        print(f"✓ Consumer allocations: {allocations}")
        return True
    except Exception as e:
        print(f"✗ Consumer logic test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all verification tests."""
    print("=" * 50)
    print("LOAN MARKET SIMULATION - VERIFICATION TESTS")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_config,
        test_data_models,
        test_consumer_logic
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            print(f"\n❌ Test {test.__name__} failed!")
    
    print("\n" + "=" * 50)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All verification tests passed!")
        print("\nYou can now run the simulation with:")
        print("python run_sim.py --test-mode")
        return 0
    else:
        print("❌ Some tests failed. Please fix the issues before running the simulation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())