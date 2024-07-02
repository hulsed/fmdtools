# -*- coding: utf-8 -*-
"""
Created on Wed Jun 26 15:06:57 2024

@author: dhulse
"""
from fmdtools.analyze.graph.model import BaseModelGraph
from fmdtools.analyze.graph.model import set_node_states, get_obj_name


class BlockGraph(BaseModelGraph):
    """Blockgraph represents the definition of a Block."""

    def nx_from_obj(self, mdl, with_methods=True, **kwargs):
        """Generate the graph of the block with containers, flows and methods."""
        return mdl.create_graph(with_methods=with_methods, **kwargs)

    def set_nx_states(self, mdl, **kwargs):
        """Get the states of the block and its attached objects."""
        basename = mdl.get_full_name()
        for role, roleobj in mdl.get_roles_as_dict().items():
            name = get_obj_name(roleobj, role, basename=basename)
            if name in self.g.nodes:
                set_node_states(self.g, roleobj, name, time=self.time)

    def set_edge_labels(self, title='edgetype', title2='', subtext='role',
                        **edge_label_styles):
        super().set_edge_labels(title=title, title2=title2, subtext=subtext,
                                **edge_label_styles)

    def set_node_labels(self, title='shortname', title2='classname', **node_label_styles):
        super().set_node_labels(title=title, title2=title2, **node_label_styles)