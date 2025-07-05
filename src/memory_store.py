"""
Long-term memory storage for simulation lessons and patterns.
"""
import sqlite3
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class Lesson:
    """A single lesson learned from a simulation."""
    lesson_type: str  # strategy, market_condition, bankruptcy, equilibrium
    lesson_text: str
    confidence: float  # 0-1 based on observation count
    conditions: Dict  # Market conditions when lesson was observed
    
    
@dataclass
class BankOutcome:
    """Final outcome for a bank in a simulation."""
    bank_name: str
    initial_strategy: str
    initial_equity: float
    initial_image: float
    initial_speed: float
    final_equity: float
    final_market_share: float
    avg_market_share: float
    survived: bool
    rounds_survived: int
    total_loans_originated: int
    avg_interest_rate: float
    

@dataclass
class StrategyPattern:
    """A generalized pattern about strategy effectiveness."""
    pattern_description: str
    success_rate: float
    conditions: str
    observation_count: int
    example_banks: List[str]


class MemoryStore:
    """Manages long-term memory database for simulation lessons."""
    
    def __init__(self, db_path: str = "memory/lessons.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_database()
        
    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Simulations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS simulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    seed INTEGER,
                    num_rounds INTEGER,
                    num_banks INTEGER,
                    num_consumers INTEGER,
                    market_metrics TEXT
                )
            """)
            
            # Lessons table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id INTEGER NOT NULL,
                    lesson_type TEXT NOT NULL,
                    lesson_text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    conditions TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
                )
            """)
            
            # Bank outcomes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bank_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id INTEGER NOT NULL,
                    bank_name TEXT NOT NULL,
                    initial_strategy TEXT NOT NULL,
                    initial_equity REAL NOT NULL,
                    initial_image REAL NOT NULL,
                    initial_speed REAL NOT NULL,
                    final_equity REAL NOT NULL,
                    final_market_share REAL NOT NULL,
                    avg_market_share REAL NOT NULL,
                    survived INTEGER NOT NULL,
                    rounds_survived INTEGER NOT NULL,
                    total_loans_originated INTEGER NOT NULL,
                    avg_interest_rate REAL NOT NULL,
                    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
                )
            """)
            
            # Strategy patterns table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_description TEXT UNIQUE NOT NULL,
                    success_rate REAL NOT NULL,
                    conditions TEXT NOT NULL,
                    observation_count INTEGER NOT NULL,
                    example_banks TEXT NOT NULL,
                    last_updated TEXT NOT NULL
                )
            """)
            
            # Create indices
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_type ON lessons(lesson_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_strategy ON bank_outcomes(initial_strategy)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_survived ON bank_outcomes(survived)")
            
    def store_simulation(self, config: Dict, seed: int, num_rounds: int, 
                        market_metrics: Dict) -> int:
        """Store a new simulation and return its ID."""
        config_str = json.dumps(config, sort_keys=True, default=str)
        config_hash = hashlib.md5(config_str.encode()).hexdigest()
        
        # Convert numpy/pandas types to native Python types for JSON serialization
        def convert_types(obj):
            if hasattr(obj, 'item'):  # numpy scalar
                return obj.item()
            elif isinstance(obj, (int, float, str, bool, type(None))):
                return obj
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [convert_types(x) for x in obj]
            else:
                return str(obj)
        
        market_metrics_serializable = convert_types(market_metrics)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO simulations 
                (timestamp, config_hash, seed, num_rounds, num_banks, num_consumers, market_metrics)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                config_hash,
                int(seed),
                int(num_rounds),
                len(config.get('banks', [])),
                config.get('num_consumers', 100),
                json.dumps(market_metrics_serializable)
            ))
            return cursor.lastrowid
            
    def store_lessons(self, simulation_id: int, lessons: List[Lesson]):
        """Store lessons from a simulation."""
        with sqlite3.connect(self.db_path) as conn:
            for lesson in lessons:
                conn.execute("""
                    INSERT INTO lessons 
                    (simulation_id, lesson_type, lesson_text, confidence, conditions, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    simulation_id,
                    lesson.lesson_type,
                    lesson.lesson_text,
                    lesson.confidence,
                    json.dumps(lesson.conditions),
                    datetime.now().isoformat()
                ))
                
    def store_bank_outcomes(self, simulation_id: int, outcomes: List[BankOutcome]):
        """Store bank outcomes from a simulation."""
        with sqlite3.connect(self.db_path) as conn:
            for outcome in outcomes:
                conn.execute("""
                    INSERT INTO bank_outcomes
                    (simulation_id, bank_name, initial_strategy, initial_equity, 
                     initial_image, initial_speed, final_equity, final_market_share,
                     avg_market_share, survived, rounds_survived, total_loans_originated,
                     avg_interest_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    simulation_id,
                    outcome.bank_name,
                    outcome.initial_strategy,
                    outcome.initial_equity,
                    outcome.initial_image,
                    outcome.initial_speed,
                    outcome.final_equity,
                    outcome.final_market_share,
                    outcome.avg_market_share,
                    int(outcome.survived),
                    outcome.rounds_survived,
                    outcome.total_loans_originated,
                    outcome.avg_interest_rate
                ))
                
    def update_strategy_patterns(self, patterns: List[StrategyPattern]):
        """Update or insert strategy patterns."""
        with sqlite3.connect(self.db_path) as conn:
            for pattern in patterns:
                # Try to update existing pattern
                cursor = conn.execute("""
                    UPDATE strategy_patterns
                    SET success_rate = ?,
                        observation_count = observation_count + ?,
                        example_banks = ?,
                        last_updated = ?
                    WHERE pattern_description = ?
                """, (
                    pattern.success_rate,
                    pattern.observation_count,
                    json.dumps(pattern.example_banks),
                    datetime.now().isoformat(),
                    pattern.pattern_description
                ))
                
                # If no existing pattern, insert new one
                if cursor.rowcount == 0:
                    conn.execute("""
                        INSERT INTO strategy_patterns
                        (pattern_description, success_rate, conditions, 
                         observation_count, example_banks, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        pattern.pattern_description,
                        pattern.success_rate,
                        pattern.conditions,
                        pattern.observation_count,
                        json.dumps(pattern.example_banks),
                        datetime.now().isoformat()
                    ))
                    
    def get_similar_market_lessons(self, market_conditions: Dict, 
                                  min_confidence: float = 0.5) -> List[Dict]:
        """Retrieve lessons from similar market conditions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get all lessons above confidence threshold
            cursor = conn.execute("""
                SELECT * FROM lessons 
                WHERE confidence >= ?
                ORDER BY confidence DESC, created_at DESC
            """, (min_confidence,))
            
            lessons = []
            for row in cursor:
                lesson_conditions = json.loads(row['conditions'])
                # Simple similarity check - can be made more sophisticated
                if self._are_conditions_similar(market_conditions, lesson_conditions):
                    lessons.append(dict(row))
                    
            return lessons
            
    def get_strategy_patterns(self, min_observations: int = 5) -> List[Dict]:
        """Get well-observed strategy patterns."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM strategy_patterns
                WHERE observation_count >= ?
                ORDER BY observation_count DESC, success_rate DESC
            """, (min_observations,))
            
            return [dict(row) for row in cursor]
            
    def get_historical_outcomes(self, strategy: Optional[str] = None,
                               survived_only: bool = False) -> List[Dict]:
        """Get historical bank outcomes, optionally filtered."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM bank_outcomes WHERE 1=1"
            params = []
            
            if strategy:
                query += " AND initial_strategy = ?"
                params.append(strategy)
                
            if survived_only:
                query += " AND survived = 1"
                
            query += " ORDER BY simulation_id DESC"
            
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor]
            
    def _are_conditions_similar(self, cond1: Dict, cond2: Dict, 
                               threshold: float = 0.8) -> bool:
        """Check if two market conditions are similar."""
        # Simple implementation - can be enhanced
        if not cond1 or not cond2:
            return False
            
        # Check if key metrics are within threshold
        metrics = ['avg_rate', 'rate_variance', 'concentration']
        similar_count = 0
        
        for metric in metrics:
            if metric in cond1 and metric in cond2:
                val1, val2 = cond1[metric], cond2[metric]
                if abs(val1 - val2) / max(val1, val2) < (1 - threshold):
                    similar_count += 1
                    
        return similar_count >= len(metrics) * threshold
        
    def calculate_pattern_confidence(self, observation_count: int) -> float:
        """Calculate confidence score based on observation count."""
        # Logarithmic confidence growth
        if observation_count == 0:
            return 0.0
        elif observation_count < 3:
            return 0.3
        elif observation_count < 10:
            return 0.5 + (observation_count - 3) * 0.05
        elif observation_count < 30:
            return 0.85 + (observation_count - 10) * 0.005
        else:
            return min(0.95, 0.85 + observation_count * 0.001)