"""
Network Query Agent
Natural Language to Predefined Cypher Query Template Mapping
Uses Google Gemini Flash 2.5 for intelligent template selection
Uses LangChain PromptTemplate for parameter replacement
"""
import os
import json
from pathlib import Path
import yaml
from neo4j import GraphDatabase
import google.generativeai as genai
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from .prompts import build_query_selector_prompt, QUERY_TEMPLATES


def load_yaml(file_path):
    """Load YAML configuration"""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


class NetworkQueryAgent:
    """Agent that maps natural language questions to predefined Cypher query templates

    Supports querying specific snapshots when multiple snapshots are loaded.
    """

    def __init__(self, snapshot_id: str = None):
        """Initialize query agent

        Args:
            snapshot_id: Optional snapshot ID to query. If None, queries all data.
        """
        # Load environment variables from .env
        load_dotenv()

        # Load Neo4j config
        config_dir = Path(__file__).parent.parent / 'graph' / 'config'
        neo4j_cfg = load_yaml(config_dir / 'neo4j.yaml')['connection']

        # Connect to Neo4j
        self.driver = GraphDatabase.driver(
            neo4j_cfg['uri'],
            auth=(neo4j_cfg['user'], neo4j_cfg['password'])
        )

        # Initialize Gemini
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set in .env file")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

        # Load query templates
        self.templates = QUERY_TEMPLATES

        # Track snapshot filter
        self.snapshot_id = snapshot_id

    def _build_system_prompt(self):
        """Build system prompt for template selection"""
        return build_query_selector_prompt()

    def select_template(self, question: str) -> dict:
        """Select appropriate query template and extract parameters

        Returns:
            dict: Contains 'reasoning', 'template', 'params', 'cypher'
        """
        # Build prompt
        prompt = f"{self._build_system_prompt()}\n\nQuestion: {question}"

        # Get LLM response
        response = self.model.generate_content(prompt)
        full_response = response.text.strip()

        # Extract reasoning
        reasoning = ""
        if "<reasoning>" in full_response and "</reasoning>" in full_response:
            reasoning_start = full_response.index("<reasoning>") + len("<reasoning>")
            reasoning_end = full_response.index("</reasoning>")
            reasoning = full_response[reasoning_start:reasoning_end].strip()

        # Extract JSON response
        if "<response>" in full_response and "</response>" in full_response:
            response_start = full_response.index("<response>") + len("<response>")
            response_end = full_response.index("</response>")
            response_json_str = full_response[response_start:response_end].strip()

            # Parse JSON
            try:
                response_data = json.loads(response_json_str)
                template_key = response_data.get('template')
                params = response_data.get('params', {})
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse template selection response: {e}")
        else:
            raise ValueError("No valid response found in LLM output")

        # Get template
        if template_key not in self.templates:
            raise ValueError(f"Unknown template: {template_key}")

        template = self.templates[template_key]

        # Build final Cypher query using LangChain PromptTemplate
        cypher_query = template['query']

        if params:
            # Create LangChain PromptTemplate with parameter mapping
            # Map "device" -> "PARAM_DEVICE", "device1" -> "PARAM_DEVICE1", etc.
            template_vars = {}
            for param_name in template['params']:
                if param_name in params:
                    # Map device -> PARAM_DEVICE
                    template_var_name = f"PARAM_{param_name.upper()}"
                    template_vars[template_var_name] = params[param_name]

            # Replace PARAM_* placeholders with actual values
            for var_name, var_value in template_vars.items():
                cypher_query = cypher_query.replace(f'"{var_name}"', f'"{var_value}"')

        return {
            'reasoning': reasoning,
            'template': template_key,
            'params': params,
            'cypher': cypher_query
        }

    def _serialize_neo4j_value(self, value):
        """Convert Neo4j objects to JSON-serializable dictionaries"""
        from neo4j.graph import Node, Relationship, Path
        from neo4j.time import DateTime, Date, Time, Duration

        if isinstance(value, Path):
            # Convert Path to a readable structure
            path_data = {
                'nodes': [],
                'relationships': [],
                'length': len(value.relationships)
            }

            # Serialize all nodes in the path
            for node in value.nodes:
                path_data['nodes'].append(self._serialize_neo4j_value(node))

            # Serialize all relationships in the path
            for rel in value.relationships:
                path_data['relationships'].append(self._serialize_neo4j_value(rel))

            return path_data
        elif isinstance(value, Node):
            # Convert Node to dict with all properties, recursively serialize
            node_dict = {
                '_id': value.id,
                '_labels': list(value.labels),
                'properties': {}
            }
            for key, val in dict(value).items():
                node_dict['properties'][key] = self._serialize_neo4j_value(val)
            return node_dict
        elif isinstance(value, Relationship):
            # Convert Relationship to dict with all properties, recursively serialize
            rel_dict = {
                '_id': value.id,
                '_type': value.type,
                '_start': value.start_node.id if hasattr(value, 'start_node') else None,
                '_end': value.end_node.id if hasattr(value, 'end_node') else None,
                'properties': {}
            }
            for key, val in dict(value).items():
                rel_dict['properties'][key] = self._serialize_neo4j_value(val)
            return rel_dict
        elif isinstance(value, (DateTime, Date, Time)):
            # Convert Neo4j datetime objects to ISO format strings
            return value.iso_format()
        elif isinstance(value, Duration):
            # Convert Duration to string
            return str(value)
        elif isinstance(value, list):
            return [self._serialize_neo4j_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_neo4j_value(v) for k, v in value.items()}
        else:
            return value

    def _add_snapshot_filter(self, cypher_query: str) -> str:
        """Add snapshot_id filter to Cypher query if snapshot is set

        Args:
            cypher_query: Original Cypher query

        Returns:
            Modified query with snapshot filter
        """
        if not self.snapshot_id:
            return cypher_query

        # Add WHERE clause to filter by snapshot_id
        # This is a simple approach - add snapshot filter to nodes/relationships
        # Note: This assumes queries follow common patterns

        # For queries matching Devices
        if "MATCH (d:Device" in cypher_query and "WHERE" not in cypher_query.split("RETURN")[0]:
            cypher_query = cypher_query.replace(
                "MATCH (d:Device",
                f"MATCH (d:Device {{snapshot_id: \"{self.snapshot_id}\"}}"
            )

        # For queries matching Interfaces
        if "MATCH (i:Interface" in cypher_query and "WHERE" not in cypher_query.split("RETURN")[0]:
            cypher_query = cypher_query.replace(
                "MATCH (i:Interface",
                f"MATCH (i:Interface {{snapshot_id: \"{self.snapshot_id}\"}}"
            )

        # For path queries, add snapshot filter
        if "shortestPath" in cypher_query or "allShortestPaths" in cypher_query:
            # Add WHERE clause after MATCH
            if "WHERE" not in cypher_query.split("RETURN")[0]:
                # Find position before RETURN
                return_pos = cypher_query.find("RETURN")
                if return_pos > 0:
                    cypher_query = (
                        cypher_query[:return_pos] +
                        f"WHERE all(n IN nodes(p) WHERE n.snapshot_id = \"{self.snapshot_id}\" OR NOT exists(n.snapshot_id)) " +
                        cypher_query[return_pos:]
                    )

        return cypher_query

    def execute_query(self, cypher_query: str, timeout: int = 30) -> dict:
        """Execute Cypher query on Neo4j with optional snapshot filtering

        Args:
            cypher_query: The Cypher query to execute
            timeout: Query timeout in seconds

        Returns:
            dict: Contains 'success', 'results', 'count', and optional 'error'
        """
        # Add snapshot filter if set
        if self.snapshot_id:
            cypher_query = self._add_snapshot_filter(cypher_query)

        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, timeout=timeout)
                # Serialize Neo4j nodes/relationships to dictionaries
                records = []
                for record in result:
                    serialized_record = {}
                    for key in record.keys():
                        serialized_record[key] = self._serialize_neo4j_value(record[key])
                    records.append(serialized_record)

                return {
                    'success': True,
                    'results': records,
                    'count': len(records)
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'results': [],
                'count': 0
            }

    def ask(self, question: str, execute: bool = True, deduplicate: bool = True) -> dict:
        """Ask a question in natural language, get template selection and results

        Args:
            question: Natural language question
            execute: Whether to execute the query on Neo4j (default: True)
            deduplicate: Whether to automatically remove duplicate results (default: True)

        Returns:
            dict: JSON with 'reasoning', 'template', 'params', 'cypher', 'results', 'count'
        """
        # Select template and build query
        selection_result = self.select_template(question)

        # Build response
        response = {
            'reasoning': selection_result['reasoning'],
            'template': selection_result['template'],
            'params': selection_result['params'],
            'cypher': selection_result['cypher']
        }

        # Execute query if requested
        if execute:
            execution_result = self.execute_query(selection_result['cypher'])

            # Deduplicate results if requested and query was successful
            if deduplicate and execution_result['success']:
                seen = set()
                unique_results = []
                for record in execution_result['results']:
                    # Create hash of record for deduplication
                    record_hash = json.dumps(record, sort_keys=True)
                    if record_hash not in seen:
                        seen.add(record_hash)
                        unique_results.append(record)

                response['results'] = unique_results
                response['count'] = len(unique_results)
            else:
                response['results'] = execution_result['results']
                response['count'] = execution_result['count']

            if not execution_result['success']:
                response['error'] = execution_result['error']

        return response

    def set_snapshot(self, snapshot_id: str):
        """Set the snapshot to query

        Args:
            snapshot_id: The snapshot ID to filter queries by
        """
        self.snapshot_id = snapshot_id
        print(f"[OK] Query agent now filtering by snapshot: {snapshot_id}")

    def get_snapshot(self) -> str:
        """Get the current snapshot filter

        Returns:
            Current snapshot ID or None if no filter set
        """
        return self.snapshot_id

    def clear_snapshot_filter(self):
        """Remove snapshot filter - query all data"""
        self.snapshot_id = None
        print("[OK] Snapshot filter cleared - querying all data")

    def close(self):
        """Close Neo4j connection"""
        self.driver.close()


def main():
    """Example usage"""
    agent = NetworkQueryAgent()

    try:
        # Example questions
        questions = [
            "Show me all devices",
            "What interfaces are down?",
            "Show OSPF neighbors for EDGE-R1",
            "Show CDP neighbors for the core switch 1"
        ]

        for question in questions:
            print(f"\n{'='*70}")
            print(f"Q: {question}")
            print('='*70)
            result = agent.ask(question)
            print(f"\nTemplate: {result['template']}")
            print(f"Parameters: {result['params']}")
            print(f"\nCypher:\n{result['cypher']}")
            print(f"\nResults: {result['count']} found")
            print("\n" + "-"*70)

    finally:
        agent.close()


if __name__ == "__main__":
    main()
