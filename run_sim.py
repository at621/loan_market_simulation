#!/usr/bin/env python3
"""Command-line runner for the loan market simulation."""

import asyncio
import argparse
import sys
import logging
from pathlib import Path
import yaml

from src.simulation import LoanMarketSimulation


def setup_logging(verbose: bool = False):
    """Configure logging for the simulation."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Reduce noise from libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)
    logging.getLogger('langchain').setLevel(logging.WARNING)


def update_config(config_path: str, args) -> str:
    """Update config based on command line arguments."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Update config based on args
    if args.rounds:
        config['simulation_params']['rounds'] = args.rounds
    
    if args.seed:
        config['seed'] = args.seed
    
    if args.test_mode:
        # Reduce rounds and use smaller model for testing
        config['simulation_params']['rounds'] = min(3, config['simulation_params']['rounds'])
        config['ai_agent_params']['model'] = 'gpt-3.5-turbo'
        config['ai_agent_params']['temperature'] = 0.5
    
    # Save temporary config if modified
    if args.rounds or args.seed or args.test_mode:
        temp_config_path = 'temp_config.yaml'
        with open(temp_config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        return temp_config_path
    
    return config_path


async def main():
    """Main entry point for the simulation."""
    parser = argparse.ArgumentParser(
        description='Run the loan market simulation with AI-powered bank agents'
    )
    
    parser.add_argument(
        '--config', 
        type=str, 
        default='config/config.yaml',
        help='Path to configuration file (default: config/config.yaml)'
    )
    
    parser.add_argument(
        '--rounds', 
        type=int, 
        help='Override number of simulation rounds'
    )
    
    parser.add_argument(
        '--seed', 
        type=int, 
        help='Override random seed for reproducibility'
    )
    
    parser.add_argument(
        '--test-mode', 
        action='store_true',
        help='Run in test mode (fewer rounds, faster model)'
    )
    
    parser.add_argument(
        '--verbose', 
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Check config exists
    if not Path(args.config).exists():
        logger.error(f"Configuration file not found: {args.config}")
        sys.exit(1)
    
    try:
        # Update config if needed
        config_path = update_config(args.config, args)
        
        # Create and run simulation
        logger.info("=" * 60)
        logger.info("LOAN MARKET SIMULATION")
        logger.info("=" * 60)
        
        if args.test_mode:
            logger.info("Running in TEST MODE - reduced rounds and faster model")
        
        simulation = LoanMarketSimulation(config_path)
        
        # Run the simulation
        await simulation.run()
        
        # Clean up temp config if created
        if config_path != args.config and Path(config_path).exists():
            Path(config_path).unlink()
        
        logger.info("=" * 60)
        logger.info("SIMULATION COMPLETE")
        logger.info("=" * 60)
        logger.info("Outputs saved:")
        logger.info("  - market_log.parquet")
        logger.info("  - portfolio_ledger.parquet")
        logger.info("  - summary.md")
        
    except KeyboardInterrupt:
        logger.info("\nSimulation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())