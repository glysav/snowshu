from typing import Type

import networkx

from snowshu.adapters.source_adapters.base_source_adapter import \
    BaseSourceAdapter
from snowshu.core.models import Relation
from snowshu.logger import Logger

logger = Logger().logger


class RuntimeSourceCompiler:

    @staticmethod   # noqa mccabe: disable=MC0001
    def compile_queries_for_relation(relation: Relation,
                                     dag: networkx.Graph,
                                     source_adapter: Type[BaseSourceAdapter],
                                     analyze: bool) -> Relation:
        """ Generates the sql statements for the given relation

            Args:
                relation (Relation): the relation to generate the sql for
                dag (Graph): the connected dependency graph that contains the relation
                source_adapter (BaseSourceAdapter): the source adapter for the sql dialect
                analyze (bool): whether to generate sql statements for analyze or actaul sampling

            Returns:
                Relation: the given relation with `compiled_query` populated
        """
        query = str()
        if relation.is_view:
            relation.core_query, relation.compiled_query = [
                source_adapter.view_creation_statement(relation) for _ in range(2)]
            return relation
        if relation.unsampled:
            query = source_adapter.unsampled_statement(relation)
        else:
            do_not_sample = False
            predicates = list()
            unions = list()
            for child in dag.successors(relation):
                # parallel edges aren't currently supported
                edge = dag.edges[relation, child]
                if edge['direction'] == 'bidirectional':
                    predicates.append(source_adapter.upstream_constraint_statement(child,
                                                                                   edge['remote_attribute'],
                                                                                   edge['local_attribute']))
                if relation.include_outliers:
                    unions.append(source_adapter.union_constraint_statement(relation,
                                                                            child,
                                                                            edge['remote_attribute'],
                                                                            edge['local_attribute'],
                                                                            relation.max_number_of_outliers))

            for parent in dag.predecessors(relation):
                edge = dag.edges[parent, relation]
                # if any incoming edge is birectional set do_not_sample flag
                do_not_sample = (edge['direction'] == 'bidirectional' or do_not_sample)
                predicates.append(source_adapter.predicate_constraint_statement(parent,
                                                                                analyze,
                                                                                edge['local_attribute'],
                                                                                edge['remote_attribute']))
                if relation.include_outliers:
                    unions.append(source_adapter.union_constraint_statement(relation,
                                                                            parent,
                                                                            edge['local_attribute'],
                                                                            edge['remote_attribute'],
                                                                            relation.max_number_of_outliers))

            query = source_adapter.sample_statement_from_relation(
                relation, (None if predicates else relation.sampling.sample_method))
            if predicates:
                query += " WHERE " + ' AND '.join(predicates)
                query = source_adapter.directionally_wrap_statement(
                    query, relation, (None if do_not_sample else relation.sampling.sample_method))
            if unions:
                query += " UNION ".join([''] + unions)

        relation.core_query = query

        if analyze:
            query = source_adapter.analyze_wrap_statement(query, relation)
        relation.compiled_query = query
        return relation
