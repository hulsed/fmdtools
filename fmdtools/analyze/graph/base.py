"""
Provides representations and visualizations of a model graph structure.

Main user-facing individual graphing classes:
- :class:`Graph`: Base graph class.
- :class:`GraphInteractor`: Class for moving graph nodes.

Private Methods:

- :func:`sff_one_trial`: Calculates one trial of the sff model
- :func:`data_average`: Averages each column in data
- :func:`data_error`: Calculates error for each column in data
- :func:`graph_factory`: Creates the default Graph for a given object.
- :func:`get_label_groups`: Creates groups of nodes/edges in terms of discrete values
  for the given tags.
"""

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
from numpy.random import random
from matplotlib.widgets import Button
from matplotlib import get_backend
from recordclass import asdict
from fmdtools.analyze.result import Result
from fmdtools.analyze.history import History
from fmdtools.analyze.common import consolidate_legend, setup_plot, prep_animation_title
from fmdtools.analyze.common import clear_prev_figure
from fmdtools.analyze.graph.style import edge_style_factory, node_style_factory
from fmdtools.analyze.graph.style import Labels, EdgeLabelStyle, LabelStyle
from fmdtools.analyze.graph.style import to_legend_label, gv_import_check


plt.rcParams['pdf.fonttype'] = 42


class Graph(object):
    """
    Base class for graphs which can be extended to represent various objects.

    Essentially provides a convenience interface for networkx to enable quick
    visualization and analysis of model properties.

    Attributes
    ----------
    g : nx.Graph
        Networkx graph to run analyses on.
    pos : dict
        Dict of node positions set using set_pos.
    edge_styles : dict
        Dict of styles for each edge set using set_edge_styles.
    node_groups : dict
        Dict of node groups by tag with key (tag1, tag2) and value [node1, node2].
    node_styles : dict
        Dict of styles for each node set using set_node_styles.
    edge_groups : dict
        Dict of edge groups by tag with key (tag1, tag2) and value [edge1, edge2].
    edge_labels : Labels
        Labels for each edge.
    node_labels : Labels
        Labels for each node.

    Parameters
    ----------
    obj: object
        must either be a networkx graph (or be a verion of Graph corresponding
                                            to the object)
    get_states: bool
        whether to get states for the graph
    **kwargs:
        keyword arguments for self.nx_from_obj
    """

    def __init__(self, obj, get_states=True, **kwargs):
        if isinstance(obj, nx.Graph):
            self.g = obj
        elif hasattr(self, 'nx_from_obj'):
            self.g = self.nx_from_obj(obj, get_states=get_states, **kwargs)

    def set_pos(self, auto=True, **pos):
        """
        Set graph positions to given positions, (automatically or manually).

        Parameters
        ----------
        auto : str, optional
            Whether to auto-layout the node position. The default is True.
        **pos : nodename=(x,y)
            Positions of nodes to set. Otherwise updates to the auto-layout or (0.5,0.5)
        """
        if not getattr(self, 'pos', False):
            self.pos = {}
        if auto:
            try:
                self.pos = nx.planar_layout(nx.MultiGraph(self.g))
            except:
                self.pos = nx.spring_layout(nx.MultiGraph(self.g))
        else:
            self.pos = {n: self.pos.get(n, (0.5, 0.5)) for n in self.g.nodes}
        self.pos.update(pos)

    def set_edge_styles(self, **edge_styles):
        """
        Set self.edge_styles and self.edge_groups given the provided edge styles.

        Parameters
        ----------
        **edge_styles : dict, optional
            Dictionary of tags, labels, and styles for the edges that overwrite the
            default. Has structure {tag:{label:kwargs}}, where kwargs are the keyword
            arguments to nx.draw_networkx_edges. The default is {"label":{}}.
        """
        self.edge_styles = {}
        if "label" not in edge_styles:
            edge_styles["label"] = {}
        self.edge_groups = get_label_groups(self.g.edges(), *edge_styles)
        for edge_group in self.edge_groups:
            self.edge_styles[edge_group] = edge_style_factory(edge_styles, edge_group)
        self.edge_style_labels = [*edge_styles.keys()]

    def set_node_styles(self, **node_styles):
        """
        Set self.node_styles and self.edge_groups given the provided node styles.

        Parameters
        ----------
        **node_styles : dict, optional
            Dictionary of tags, labels, and style kwargs for the nodes that overwrite
            the default. Has structure {tag:{label:kwargs}}, where kwargs are the
            keyword arguments to nx.draw_networkx_nodes. The default is {"label":{}}.
        """
        self.node_styles = {}
        if "label" not in node_styles:
            node_styles['label'] = {}
        self.node_groups = get_label_groups(self.g.nodes(), *node_styles)
        for node_group in self.node_groups:
            self.node_styles[node_group] = node_style_factory(node_styles, node_group)
        self.node_style_labels = [*node_styles.keys()]

    def set_edge_labels(self, title='label', title2='', subtext='states',
                        **edge_label_styles):
        """
        Create labels using Labels.from_iterator for the edges in the graph.

        Parameters
        ----------
        title : str, optional
            property to get for title text. The default is 'id'.
        title2 : str, optional
            property to get for title text after the colon. The default is ''.
        subtext : str, optional
            property to get for the subtext. The default is 'states'.
        **edge_label_styles : dict
            LabelStyle arguments to overwrite.
        """
        self.edge_labels = Labels.from_iterator(self.g, self.g.edges, EdgeLabelStyle,
                                                title=title, title2=title2,
                                                subtext=subtext, **edge_label_styles)

    def set_node_labels(self, title='id', title2='', subtext='', **node_label_styles):
        """
        Create labels using Labels.from_iterator for the nodes in the graph.

        Parameters
        ----------
        title : str, optional
            Property to get for title text. The default is ‘id’.
        title2 : str, optional
            Property to get for title text after the colon. The default is ‘’.
        subtext : str, optional
            property to get for the subtext. The default is ‘’.
        node_label_styles :  dict
            LabelStyle arguments to overwrite.
        """
        self.node_labels = Labels.from_iterator(self.g, self.g.nodes, LabelStyle,
                                                title=title, title2=title2,
                                                subtext=subtext, **node_label_styles)

    def add_node_groups(self, **node_groups):
        """
        Create arbitrary groups of nodes to displayed with different styles.

        Parameters
        ----------
        **node_groups : iterable
            nodes in groups. see example.

        e.g.,::
        graph.add_node_groups(group1=('node1', 'node2'), group2=('node3'))
        graph.set_node_styles(group={'group1':{'color':'green'},
                                     'group2':{'color':'red'}})
        graph.draw()

        would show two different groups of nodes, one with green nodes, and the other
        with red nodes
        """
        group_attrs = {}
        for node_group, nodes in node_groups.items():
            group_attrs.update({n: node_group for n in nodes})
        group_attrs.update({n: '' for n in self.g.nodes if n not in group_attrs})
        nx.set_node_attributes(self.g, group_attrs, 'group')

    def set_resgraph(self, other=False):
        """
        Process results for results graphs (show faults and degradations).

        Parameters
        ----------
        other : Graph, optional
            Graph to compare with (for degradations). The default is False.
        """
        if not other:
            other = self
        self.set_degraded(other)
        self.set_node_styles(degraded={}, faulty={})
        self.set_node_labels(title='id', subtext='faults_and_indicators')

    def set_degraded(self, other):
        """
        Set 'degraded' state in networkx graph.

        Uses difference between states with another Graph object.

        Parameters
        ----------
        other : Graph
            (assumed nominal) Graph to compare to
        """
        g = self.g
        nomg = other.g
        for node in g.nodes:
            degstates = (g.nodes[node]['states'] != nomg.nodes[node]['states'])
            degindicators = (set(g.nodes[node]['indicators']) != set(nomg.nodes[node]['indicators']))
            g.nodes[node]['degraded'] = degstates or degindicators
            g.nodes[node]['faulty'] = any(g.nodes[node].get('faults', []))

    def set_heatmap(self, heatmap, cmap=plt.cm.coolwarm, default_color_val=0.0):
        """
        Set the association and plotting of a heatmap on a graph.

        e.g.,::
        graph.set_heatmap({'node_1':1.0, 'node_2': 0.0, 'node_3':0.5})
        graph.draw()

        Should draw node_1 the bluest, node_2 the reddest, and node_3 in between.

        Parameters
        ----------
        heatmap : dict/result
            dict/result with keys corresponding to the nodes and values in the range
            of a heatmap (0-1)
        cmap : mpl.Colormap, optional
            Colormap to use for the heatmap. The default is plt.cm.coolwarm.
        default_color_val : float, optional
            Value to use if a node is not in the heatmap dict. The default is 0.0.
        """
        self.set_node_styles()
        for label, nodes in self.node_groups.items():
            nodes_colors = [heatmap[node] if node in heatmap else default_color_val
                            for node in nodes]
            self.node_styles[label].node_color = nodes_colors
            self.node_styles[label].cmap = cmap

    def set_properties(self, **kwargs):
        """Set properties using kwargs where there is a given set_kwarg command."""
        for to_set in ['pos', 'edge_styles', 'edge_labels',
                       'node_styles', 'node_labels']:
            if to_set in kwargs or not hasattr(self, to_set):
                set_func = getattr(self, 'set_'+to_set)
                set_func(**kwargs.pop(to_set, {}))
        return kwargs

    def draw(self, figsize=(12, 10), title="", fig=False, ax=False, withlegend=True,
             legend_bbox=(1, 0.5), legend_loc="center left", legend_labelspacing=2,
             legend_borderpad=1, **kwargs):
        """
        Draw a graph with given styles corresponding to the node/edge properties.

        Parameters
        ----------
        figsize : tuple, optional
            Size for the figure (plt.figure arg). The default is (12,10).
        title : str, optional
            Title for the plot. The default is "".
        fig : bool, optional
            matplotlib figure to project on (if provided). The default is False.
        ax : bool, optional
            matplotlib axis to plot on (if provided). The default is False.
        withlegend : bool, optional
            Whether to include a legend. The default is True.
        legend_bbox : tuple, optional
            bbox to anchor the legend to. The default is (1,0.5), which places legend
            on the right.
        legend_loc : str, optional
            loc argument for plt.legend. The default is "center left".
        legend_labelspacing : float, optional
            labelspacing argument for plt.legend. the default is 2.
        legend_borderpad : str, optional
            borderpad argument for plt.legend. the default is 1.
        **kwargs : kwargs
            Arguments for various supporting functions:
            (set_pos, set_edge_styles, set_edge_labels, set_node_styles,
            set_node_labels, etc)

        Returns
        -------
        fig : matplotlib figure
            matplotlib figure to draw
        ax : matplotlib axis
            Ax in the figure
        """
        fig, ax = setup_plot(figsize=figsize, fig=fig, ax=ax)
        self.set_properties(**kwargs)
        # edge handles: used to fix edge legend bug in matplotlib/networkx
        edge_handles = []
        for label, edges in self.edge_groups.items():
            legend_label = to_legend_label(label, self.edge_style_labels)
            nx.draw_networkx_edges(self.g, self.pos, edges,
                                   **self.edge_styles[label].nx_kwargs(),
                                   label=legend_label, ax=ax)
            edge_handles.append(self.edge_styles[label].nx_legend_line(legend_label))

        for level in self.edge_labels.iter_groups():
            nx.draw_networkx_edge_labels(self.g, self.pos, self.edge_labels[level],
                                         **self.edge_labels[level+'_style'].kwargs(),
                                         ax=ax)

        for label, nodes in self.node_groups.items():
            legend_label = to_legend_label(label, self.node_style_labels)
            nx.draw_networkx_nodes(self.g, self.pos, nodes,
                                   **self.node_styles[label].kwargs(),
                                   label=legend_label, ax=ax)

        for level in self.node_labels.iter_groups():
            nx.draw_networkx_labels(self.g, self.pos, self.node_labels[level],
                                    **self.node_labels[level+'_style'].kwargs(), ax=ax)

        if withlegend:
            consolidate_legend(ax, labelspacing=legend_labelspacing,
                               borderpad=legend_borderpad,
                               bbox_to_anchor=legend_bbox,
                               loc=legend_loc,
                               add_handles=edge_handles)
        plt.axis('off')

        if title:
            ax.set_title(title)
        return fig, ax

    def move_nodes(self, **kwargs):
        """
        Set the position of nodes for plots in analyze.graph using a graphical tool.

        Note: make sure matplotlib is set to plot in an external window
        (e.g., using '%matplotlib qt)

        Parameters
        ----------
        **kwargs : kwargs
            keyword arguments for graph.draw

        Returns
        -------
        p : GraphIterator
            Graph Iterator (in analyze.Graph)
        """
        plt.ion()
        p = GraphInteractor(self, **kwargs)
        if 'inline' in get_backend():
            print("Cannot place nodes in inline version of plot. Use '%matplotlib qt'" +
                  " (or '%matplotlib osx') to open in external window")
        return p

    def draw_from(self, time, history=History(), **kwargs):
        """
        Draws the graph with degraded/fault data at a given time.

        Parameters
        ----------
        time : int
            Time to draw the graph (in the history)
        history : History, optional
            History with nominal and faulty history. The default is History().
        **kwargs : **kwargs
            arguments for Graph.draw

        Returns
        -------
        fig : matplotlib figure
            matplotlib figure to draw
        ax : matplotlib axis
            Ax in the figure
        """
        faulty = history.get_faulty_hist(*self.g.nodes,
                                         withtotal=False,
                                         withtime=False).get_slice(time)
        fault_nodes = {n: bool(faulty.get(n, 0)) for n in self.g.nodes}
        nx.set_node_attributes(self.g, fault_nodes, 'faulty')

        faults = Result(history.get_faults_hist(*self.g.nodes).get_slice(time))
        faults_nodes = {n: [k for k, v in faults.get(n).items() if v]
                        if fault_nodes.get(n)
                        else [] for n in self.g.nodes}
        nx.set_node_attributes(self.g, faults_nodes, 'faults')

        degraded = history.get_degraded_hist(*self.g.nodes,
                                             withtotal=False,
                                             withtime=False).get_slice(time)
        deg_nodes = {n: bool(degraded.get(n, 0)) for n in self.g.nodes}
        nx.set_node_attributes(self.g, deg_nodes, 'degraded')

        # nx.set_node_attributes(self.g, state_nodes, 'states')
        self.set_node_styles(degraded={}, faulty={})
        self.set_node_labels(title='id', subtext='faults')
        kwargs = prep_animation_title(time, **kwargs)
        clear_prev_figure(**kwargs)
        return self.draw(**kwargs)

    def animate(self, history, times='all', figsize=(6, 4), **kwargs):
        """
        Successively animate a plot using Graph.draw_from.

        Parameters
        ----------
        history : History
            History with faulty and nominal states
        times : list, optional
            List of times to animate over. The default is 'all'
        figsize : tuple, optional
            Size for the figure. The default is (6,4)
        **kwargs : kwargs

        Returns
        -------
        ani : matplotlib.animation.FuncAnimation
            Animation object with the given frames
        """
        return history.animate(self.draw_from, times=times, figsize=figsize,
                               withlegend=False, **kwargs)

    def draw_graphviz(self, filename='', filetype='png', **kwargs):
        """
        Draw the graph using pygraphviz for publication-quality figures.

        Note that the style may not match one-to-one with the defined none/edge styles.

        Parameters
        ----------
        filename : str, optional
            Name to save the figure to (if saving the figure). The default is ''.
        filetype : str, optional
            Type of file to safe. The default is 'png'.
        **kwargs : kwargs
            Arguments for various supporting functions:
            (set_pos, set_edge_styles, set_edge_labels, set_node_styles,
            set_node_labels, etc)
            Can also provide kwargs for Digraph() initialization.

        Returns
        -------
        dot : PyGraphviz DiGraph
            Graph object corresponding to the figure.
        """
        kwargs = self.set_properties(**kwargs)
        from IPython.display import display, SVG
        Digraph, Graph = gv_import_check()
        dot = Digraph(graph_attr=kwargs)

        for group, nodes in self.node_groups.items():
            gv_kwargs = self.node_styles[group].as_gv_kwargs()
            for node in nodes:
                label = ""
                if node in self.node_labels.title:
                    label += self.node_labels.title[node]
                if node in self.node_labels.subtext:
                    label += '\n'+str(self.node_labels.subtext[node])

                dot.node(node, style="filled", label=label, **gv_kwargs)

        for group, edges in self.edge_groups.items():
            gv_kwargs = self.edge_styles[group].as_gv_kwargs()
            for edge in edges:
                label = ""
                if edge in self.edge_labels.title:
                    label += self.edge_labels.title[edge]
                if edge in self.edge_labels.subtext:
                    label += '\n'+self.edge_labels.subtext[edge]

                dot.edge(edge[0], edge[1], label=label, **gv_kwargs)

        if filename:
            dot.render(filename=filename, format=filetype)
        else:
            display(SVG(dot._repr_image_svg_xml()))
        return dot

    def calc_aspl(self):
        """
        Compute average shortest path length of

        Returns
        -------
        aspl: float
            Average shortest path length
        """
        return nx.average_shortest_path_length(self.g)

    def calc_modularity(self):
        """
        Compute network modularity of the graph.

        Returns
        -------
        modularity : Modularity
        """
        from networkx.algorithms.community import greedy_modularity_communities
        from networkx.algorithms.community.quality import modularity
        communities = list(greedy_modularity_communities(self.g))
        return modularity(self.g, communities)

    def find_bridging_nodes(self):
        """
        Determine bridging nodes in a graph representation of model mdl.

        Returns
        -------
        bridgingNodes : list of bridging nodes
        """
        from networkx.algorithms.community import greedy_modularity_communities
        g = self.g
        communitiesRaw = list(greedy_modularity_communities(g))
        communities = [list(x) for x in communitiesRaw]
        numCommunities = len(communities)
        nodes = list(g.nodes)
        numNodes = len(nodes)
        bridgingNodes = list()
        nodeEdges = list()
        for i in range(0, numNodes):
            nodeEdges.append(list(g.edges(nodes[i])))
            lenNodeEdges = len(nodeEdges[i])
            for j in range(numCommunities):
                if nodes[i] in communities[j]:
                    communityIdx = j
            for j in range(lenNodeEdges):
                nodeEdgePair = list(nodeEdges[i][j])
                if nodeEdgePair[1] in communities[communityIdx]:
                    pass
                else:
                    bridgingNodes.append(nodes[i])
        bridgingNodes = sorted(list(set(bridgingNodes)))
        return bridgingNodes

    def plot_bridging_nodes(self, title='bridging nodes',
                            node_kwargs={'node_color': 'red'}, **kwargs):
        """
        Plot bridging nodes using self.draw().

        Parameters
        ----------
        title : str, optional
            Title for the plot. The default is 'bridging nodes'.
        node_kwargs : dict, optional
            Non-default fields for NodeStyle
        **kwargs : kwargs
            kwargs for Graph.draw

        Returns
        -------
        fig : matplotlib figure
            Figure
        """
        bridgingnodes = self.find_bridging_nodes()
        self.add_node_groups(bridging_nodes=bridgingnodes)
        self.set_node_styles(group={'bridging_nodes': node_kwargs})
        fig = self.draw(title=title, **kwargs)
        return fig

    def find_high_degree_nodes(self, p=90):
        """
        Determine highest degree nodes, up to percentile p, in graph.

        Parameters
        ----------
        p : int (optional)
            percentile of degrees to return, between 0 and 100

        Returns
        -------
        highDegreeNodes : list of high degree nodes in format (node,degree)
        """
        g = self.g
        d = list(g.degree())

        def take_second(elem):
            return elem[1]
        sortedNodes = sorted(d, key=take_second, reverse=True)
        sortedDegrees = [x[1] for x in sortedNodes]
        sortedDegreesSet = set(sortedDegrees)
        sortedDegreesUnique = list(sortedDegreesSet)
        sortedDegreesUniqueArray = np.array(sortedDegreesUnique)
        topPercentileDegree = np.percentile(sortedDegreesUniqueArray, p)
        numNodes = len(sortedNodes)
        highDegreeNodes = [sortedNodes[0]]
        for i in range(1, numNodes):
            if sortedNodes[i][1] < topPercentileDegree:
                pass
            else:
                highDegreeNodes.append(sortedNodes[i])
        return highDegreeNodes

    def plot_high_degree_nodes(self, p=90, title='', node_kwargs={'node_color': 'red'},
                               **kwargs):
        """
        Plot high-degree nodes using self.draw()

        Parameters
        ----------
        p : int (optional)
            percentile of degrees to return, between 0 and 100
        title : str, optional
            Title for the plot. The default is 'High Degree Nodes'.
        node_kwargs : dict : kwargs to overwrite the default NodeStyle
        **kwargs : kwargs
            kwargs for Graph.draw

        Returns
        -------
        fig : matplotlib figure
            Figure
        """
        if not title:
            title = 'High Degree Nodes ('+str(p)+'th Percentile)'
        hdnodes = self.find_high_degree_nodes()
        self.add_node_groups(high_degree_nodes=[h[0] for h in hdnodes])
        self.set_node_styles(group={'high_degree_nodes': node_kwargs})
        fig = self.draw(title=title, **kwargs)
        return fig

    def calc_robustness_coefficient(self, trials=100, seed=False):
        """
        Compute robustness coefficient of graph representation of model mdl.

        Parameters
        ----------
        trials : int
            number of times to run robustness coefficient algorithm
            (result is averaged over all trials)
        seed : int
            optional seed to instantiate test with

        Returns
        -------
        RC : robustness coefficient
        """
        g = self.g
        if seed:
            rng = np.random.default_rng(seed=seed)
        else:
            rng = np.random.default_rng()

        trialsRC = list()
        for itr in range(trials):
            tmp = g.copy()
            N = float(len(tmp))
            largestCC = max(nx.connected_components(tmp), key=len)
            s = [float(len(largestCC))]
            rs = rng.choice(range(int(s[0])), int(s[0]), replace=False)
            nodes = list(g)
            for i in range(int(s[0])-1):
                tmp.remove_node(nodes[rs[i]])
                largestCC = max(nx.connected_components(tmp), key=len)
                s.append(float(len(largestCC)))
            trialsRC.append((200*sum(s)-100*s[0])/N/N)
        RC = sum(trialsRC)/len(trialsRC)
        return RC

    def plot_degree_dist(self):
        """
        Plot degree distribution of graph representation of model mdl.

        Returns
        -------
        fig : matplotlib figure
            plot of distribution
        """
        import math
        g = self.g
        degrees = [g.degree(n) for n in g.nodes()]
        degreesSet = set(degrees)
        degreesUnique = list(degreesSet)
        freq = [degrees.count(n) for n in degreesUnique]
        maxFreq = max(freq)
        freqint = list(range(0, maxFreq+1))
        degreeint = list(range(min(degrees), math.ceil(max(degrees))+1))
        # TODO degreeSet looks to be not used, consider removing - JLO
        degreesSet = set(degrees)
        degreesUnique = list(degrees)
        numDegreesUnique = len(degreesUnique)

        fig = plt.figure()
        plt.hist(degrees, bins=np.arange(numDegreesUnique)-0.5)
        plt.xticks(degreeint)
        plt.yticks(freqint)
        plt.title('Degree distribution')
        plt.xlabel('Degree')
        plt.ylabel('Frequency')
        plt.show()
        return fig

    def sff_model(self, endtime=5, pi=.1, pr=.1,
                  num_trials=100, start_node='random', error_bar_option='off'):
        """
        susc-fix-fail model.

        Parameters
        ----------
        endtime: int
            simulation end time
        pi : float
            infection (failure spread) rate
        pr : float
            recovery (fix) rate
        num_trials : int
            number of times to run the epidemic model, default is 100
        error_bar_option : str
            option for plotting error bars (first to third quartile), default is off
        start_node : str
            start node to use in the trial. default is 'random'

        Returns
        -------
        fig: plot of susc, fail, and fix nodes over time
        """
        g = self.g
        if start_node == 'random':
            nodes = list(g.nodes)
            start_node_selected = nodes[random.randint(0, len(nodes))]
        else:
            start_node_selected = start_node
        num_susc_all_trials = []
        num_fail_all_trials = []
        num_fix_all_trials = []
        for trials in range(0, num_trials):
            s_f_f = sff_one_trial(start_node_selected, g, endtime=endtime, pi=pi, pr=pr)
            num_susc_trial, num_fail_trial, num_fix_trial = s_f_f
            num_susc_all_trials.append(num_susc_trial)
            num_fail_all_trials.append(num_fail_trial)
            num_fix_all_trials.append(num_fix_trial)
        num_susc_average = data_average(num_susc_all_trials)
        num_fail_average = data_average(num_fail_all_trials)
        num_fix_average = data_average(num_fix_all_trials)

        fig = plt.figure()
        time_list = range(0, endtime+1)
        if error_bar_option == 'on':
            num_susc_lower_error, num_susc_upper_error = data_error(num_susc_all_trials,
                                                                    num_susc_average)
            num_fail_lower_error, num_fail_upper_error = data_error(num_fail_all_trials,
                                                                    num_fail_average)
            num_fix_lower_error, num_fix_upper_error = data_error(num_fix_all_trials,
                                                                  num_fix_average)
            num_susc_asymmetric_error = np.abs([num_susc_lower_error, num_susc_upper_error])
            num_fail_asymmetric_error = np.abs([num_fail_lower_error, num_fail_upper_error])
            num_fix_asymmetric_error = np.abs([num_fix_lower_error, num_fix_upper_error])
            plt.errorbar(time_list, num_susc_average,
                         yerr=num_susc_asymmetric_error, fmt='-o', label='Susceptible')
            plt.errorbar(time_list, num_fail_average,
                         yerr=num_fail_asymmetric_error, fmt='-o', label='Failed')
            plt.errorbar(time_list, num_fix_average,
                         yerr=num_fix_asymmetric_error, fmt='-o', label='Fixed')
        else:
            plt.plot(time_list, num_susc_average, label='Susceptible')
            plt.plot(time_list, num_fail_average, label='Failed')
            plt.plot(time_list, num_fix_average, label='Fixed')
        plt.legend()
        plt.title('SFF model')
        plt.xlabel('Time steps')
        plt.ylabel('Number of nodes')
        plt.show()
        return fig

    def get_obj_state(self, obj):
        if hasattr(obj, 's'):
            return asdict(obj.s)
        else:
            return {}

    def get_obj_mode(self, obj):
        if hasattr(obj, 'm'):
            return [*obj.m.faults]
        else:
            return []


def sff_one_trial(start_node_selected, g, endtime=5, pi=.1, pr=.1):
    """
    Calculate one trial of the sff model.

    Parameters
    ----------
    start_node_selected : str
        node to start the trial from
    g : networkx graph
        graph to run the trial over
    endtime: int
        simulation end time
    pi : float
        infection (failure spread) rate
    pr : float
        recovery (fix) rate
    """
    rng = np.random.default_rng()
    nodes = list(g.nodes)
    num_nodes = len(nodes)
    time = 0
    susc_nodes = nodes
    susc_nodes.remove(start_node_selected)
    fail_nodes = [start_node_selected]
    fix_nodes = []
    num_susc = [num_nodes-1]
    num_fail = [1]
    num_fix = [0]
    while time < endtime:
        time = time + 1
        new_exposed_nodes = []
        for i in range(0, len(fail_nodes)):
            n = list(g.neighbors(fail_nodes[i]))
            new_exposed_nodes.extend(n)
        ri_list = [rng.random() for iter in range(len(new_exposed_nodes))]
        new_fail_nodes = []
        for i in range(0, len(new_exposed_nodes)):
            if new_exposed_nodes[i] in fix_nodes:
                pass
            else:
                if ri_list[i] <= pi:
                    new_fail_nodes.append(new_exposed_nodes[i])
        new_fail_nodes_set = set(new_fail_nodes)
        new_fail_nodes = list(new_fail_nodes_set)
        for i in range(0, len(new_fail_nodes)):
            if new_fail_nodes[i] in fail_nodes:
                pass
            else:
                susc_nodes.remove(new_fail_nodes[i])
        fail_nodes.extend(new_fail_nodes)
        fail_nodes_set = set(fail_nodes)
        fail_nodes = list(fail_nodes_set)
        rf_list = [rng.random() for iter in range(len(fail_nodes))]
        new_fix_nodes = []
        for i in range(0, len(fail_nodes)):
            if rf_list[i] <= pr:
                new_fix_nodes.append(fail_nodes[i])
        fix_nodes.extend(new_fix_nodes)
        fail_nodes = list(set(fail_nodes)-set(new_fix_nodes))
        num_susc.append(len(susc_nodes))
        num_fail.append(len(fail_nodes))
        num_fix.append(len(fix_nodes))
    return num_susc, num_fail, num_fix


def data_average(data):
    """Average each column in data."""
    list_average = []
    for i in range(0, len(data[0])):
        list_average.append(sum(x[i] for x in data)/len(data))
    return list_average


def data_error(data, average):
    """
    Calculate error for each column in data.

    Parameters
    ----------
    data : list
        List of lists from sff_model
    average : list
        Average of data generated from sff_model over time

    Returns
    -------
    lower_error : float
        Lower bound of error
    upper_error : float
        Upper bound of error
    """
    q1 = []
    q3 = []
    for i in range(0, len(data[0])):
        current_array = np.array([float(x[i]) for x in data])
        q1.append(np.percentile(current_array, 25))
        q3.append(np.percentile(current_array, 75))
    lower_error = [x - y for x, y in zip(average, q1)]
    upper_error = [x - y for x, y in zip(q3, average)]
    return lower_error, upper_error


def get_label_groups(iterator, *tags):
    """
    Create groups of nodes/edges in terms of discrete values for the given tags.

    Parameters
    ----------
    iterator : iterable
        e.g., nx.graph.nodes(), nx.graph.edges()
    *tags : list
        Tags to find in the graph object (e.g., `label`, `status`, etc.)

    Returns
    -------
    label_groups : dict
        Dict of groups of nodes/edges with given tag values. With structure::
        {(tagval1, tagval2...):[list_of_nodes]}
    """
    try:
        labels = {k: tuple(vals[tag] for tag in tags) for k, vals in iterator.items()}
    except KeyError as e:
        unable = {k: tuple(tag for tag in tags if tag not in vals)
                  for k, vals in iterator.items()}
        raise Exception("The following keys lack the following tags: " +
                        str(unable)) from e
    label_groups = {}
    for key, label in labels.items():
        if label in label_groups:
            label_groups[label].append(key)
        else:
            label_groups[label] = [key]
    return label_groups


class GraphInteractor:
    """
    A simple interactive graph for consistent node placement, etc.

    Used in set_pos to set node positions.
    """

    showverts = True
    epsilon = 0.2  # max pixel distance to count as a vertex hit

    def __init__(self, g_obj, **kwargs):
        """
        Initialize the interactive graph.

        Parameters
        ----------
        g_obj : Graph
            Graph object to plot interactively
        kwargs : dict
            kwargs for Graph.draw
        """
        self.t = 0
        gridspec_kw = {'height_ratios': [1, 10]}
        self.fig, (self.bax, self.ax) = plt.subplots(2, gridspec_kw=gridspec_kw)
        self.kwargs = kwargs
        self.g_obj = g_obj
        self.g_obj.set_pos()
        self.refresh_plot()
        self._clicked_node = None
        bnext = Button(self.bax, 'Print positions')
        bnext.on_clicked(self.print_pos)
        self.fig.canvas.mpl_connect('button_press_event', self.on_button_press)
        self.fig.canvas.mpl_connect('button_release_event', self.on_button_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)

    def get_closest_point(self, event):
        """Find the closest node to the given click to see if it should be move."""
        pt_x = np.array([x[0] for x in self.g_obj.pos.values()])
        pt_y = np.array([x[1] for x in self.g_obj.pos.values()])
        pt_names = [*self.g_obj.pos.keys()]

        dists = np.hypot(pt_x - event.xdata, pt_y - event.ydata)
        closest_pt = pt_names[dists.argmin()]
        if dists.min() >= self.epsilon:
            closest_pt = None
        return closest_pt

    def on_button_press(self, event):
        """Determine what to do when a button is pressed."""
        if event.inaxes is None:
            return
        if event.inaxes == self.bax:
            self.print_pos()
            return
        if event.button != 1:
            return
        self._clicked_node = self.get_closest_point(event)

    def on_button_release(self, event):
        """Determine what to do when the mouse is released."""
        if event.button != 1:
            return
        self._clicked_node = None
        self.ax.clear()
        self.refresh_plot()

    def on_mouse_move(self, event):
        """Change the node position when the user drags it."""
        if not self.showverts:
            return
        if event.inaxes is None:
            return
        if event.button != 1:
            return
        x, y = event.xdata, event.ydata
        if self._clicked_node:
            self.g_obj.pos[self._clicked_node] = [x, y]

    def refresh_plot(self):
        """Refresh the plot with the new positions."""
        self.g_obj.pos = {pt: np.round(loc, 2) for pt, loc in self.g_obj.pos.items()}
        self.g_obj.draw(fig=self.fig, ax=self.ax, withlegend=False, **self.kwargs)
        self.ax.set_xlim(-1, 1)
        self.ax.set_ylim(-1, 1)
        limits = plt.axis('on')

        self.ax.tick_params(left=True, bottom=True, labelleft=True, labelbottom=True)
        self.ax.set_aspect('equal')
        self.ax.grid(True, which='both')
        self.ax.set_title('Drag nodes to change their positions')
        self.t += 1
        plt.pause(0.001)

    def print_pos(self):
        """Print the current node positions in the graph from the console."""
        print({k: list(v) for k, v in self.g_obj.pos.items()})


def graph_factory(obj, **kwargs):
    """
    Create the default Graph for a given object. Used in fmdtools.sim.get_result.

    Parameters
    ----------
    obj : object
        object corresponding to a specific graph type
    **kwargs : kwargs
        Keyword arguments for the Graph class

    Returns
    -------
    graph : Graph
        Graph of the appropriate (default) class
    """
    from fmdtools.define.architecture.function import FunctionArchitecture
    from fmdtools.define.flow.multiflow import MultiFlow
    from fmdtools.define.flow.commsflow import CommsFlow
    from fmdtools.define.architecture.action import ActionArchitecture

    if isinstance(obj, FunctionArchitecture):
        from fmdtools.analyze.graph.architecture import FunctionArchitectureGraph
        return FunctionArchitectureGraph(obj, **kwargs)
    elif isinstance(obj, CommsFlow):
        from fmdtools.analyze.graph.flow import CommsFlowGraph
        return CommsFlowGraph(obj, **kwargs)
    elif isinstance(obj, MultiFlow):
        from fmdtools.analyze.graph.flow import MultiFlowGraph
        return MultiFlowGraph(obj, **kwargs)
    elif isinstance(obj, ActionArchitecture):
        from fmdtools.analyze.graph.architecture import ActionArchitectureGraph
        return ActionArchitectureGraph(obj, **kwargs)
    else:
        raise Exception("No default graph for class "+obj.__class__.__name__)
