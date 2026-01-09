"""
Neo4j Database Connector
wrapper for Neo4j graph database operations
"""
from neo4j import GraphDatabase
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Neo4jConnector:
    """Neo4j database connection and query execution"""

    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        """
        Initialize Neo4j connection

        Args:
            uri: Neo4j bolt URI
            user: Database username
            password: Database password
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None
        self._connect()

    def _connect(self):
        """Establish connection to Neo4j"""
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # Verify connectivity
            self.driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self.uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    def execute_query(self, query, parameters=None):
        """
        Execute a Cypher query

        Args:
            query: Cypher query string
            parameters: Dictionary of query parameters

        Returns:
            List of result records
        """
        if not self.driver:
            raise ConnectionError("Not connected to Neo4j")

        parameters = parameters or {}

        try:
            with self.driver.session() as session:
                result = session.run(query, parameters)
                records = [record.data() for record in result]
                logger.debug(f"Query executed: {query[:100]}... ({len(records)} results)")
                return records
        except Exception as e:
            logger.error(f"Query failed: {e}\nQuery: {query}")
            raise

    def execute_write(self, query, parameters=None):
        """
        Execute a write transaction (CREATE, MERGE, SET, DELETE)

        Args:
            query: Cypher query string
            parameters: Dictionary of query parameters

        Returns:
            Result summary
        """
        if not self.driver:
            raise ConnectionError("Not connected to Neo4j")

        parameters = parameters or {}

        try:
            with self.driver.session() as session:
                result = session.execute_write(
                    lambda tx: tx.run(query, parameters).consume()
                )
                logger.debug(f"Write executed: {query[:100]}...")
                return result
        except Exception as e:
            logger.error(f"Write failed: {e}\nQuery: {query}")
            raise

    def clear_database(self):
        """
        Delete all nodes and relationships in the database
        WARNING: This will wipe the entire graph!
        """
        logger.warning("Clearing entire Neo4j database...")
        try:
            # Delete in batches to avoid memory issues
            self.execute_write("MATCH (n) DETACH DELETE n")
            logger.info("Database cleared successfully")
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            raise

    def create_constraints(self):
        """
        Create unique constraints and indexes for better performance
        """
        logger.info("Creating database constraints and indexes...")

        constraints = [
            # Unique constraints
            "CREATE CONSTRAINT device_hostname IF NOT EXISTS FOR (d:Device) REQUIRE d.hostname IS UNIQUE",
            "CREATE CONSTRAINT interface_id IF NOT EXISTS FOR (i:Interface) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT vlan_id IF NOT EXISTS FOR (v:VLAN) REQUIRE v.vlan_id IS UNIQUE",
            "CREATE CONSTRAINT mac_address IF NOT EXISTS FOR (m:MACAddress) REQUIRE m.mac_address IS UNIQUE",
        ]

        for constraint in constraints:
            try:
                self.execute_write(constraint)
                logger.debug(f"Constraint created: {constraint[:50]}...")
            except Exception as e:
                # Constraint might already exist, just log and continue
                logger.debug(f"Constraint skipped (may already exist): {e}")

    def get_node_count(self):
        """
        Get total count of nodes in database

        Returns:
            int: Total node count
        """
        result = self.execute_query("MATCH (n) RETURN count(n) as count")
        return result[0]['count'] if result else 0

    def get_relationship_count(self):
        """
        Get total count of relationships in database

        Returns:
            int: Total relationship count
        """
        result = self.execute_query("MATCH ()-[r]->() RETURN count(r) as count")
        return result[0]['count'] if result else 0

    def get_stats(self):
        """
        Get database statistics

        Returns:
            dict: Database statistics
        """
        stats = {
            'nodes': self.get_node_count(),
            'relationships': self.get_relationship_count()
        }

        # Get node counts by label
        label_result = self.execute_query(
            "MATCH (n) RETURN labels(n)[0] as label, count(n) as count"
        )
        stats['node_labels'] = {r['label']: r['count'] for r in label_result}

        # Get relationship counts by type
        rel_result = self.execute_query(
            "MATCH ()-[r]->() RETURN type(r) as type, count(r) as count"
        )
        stats['relationship_types'] = {r['type']: r['count'] for r in rel_result}

        return stats

    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")

    def __enter__(self):
        """Context manager support"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.close()
        return False

    def __repr__(self):
        """String representation"""
        status = "connected" if self.driver else "disconnected"
        return f"<Neo4jConnector {self.uri} ({status})>"
