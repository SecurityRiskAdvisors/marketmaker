from enum import Enum, auto
import click
import graphviz
import copy

from libmm.sql import Blueprint
from libmm.extension import AbstractUserHook, UserHookSetting, EventTypes
from libmm.utils import resolve_str_or_path
from libmm.type import OutputPrefixes
from libmm.log import logger


"""
This extension generates an SVG of a Graphviz graph based on the relationships between 
Bluepint groups and Variant TIDs
"""


class GraphvizSettings(Enum):
    Svg = auto()


class GraphvizHook(AbstractUserHook):
    def __init__(self):
        self.enabled = False
        self.__settings = {
            GraphvizSettings.Svg: UserHookSetting(name="svg_path", parent=self),
        }
        self._graph = None

    @property
    def name(self):
        return "graphviz"

    @property
    def settings(self):
        return list(self.__settings.values())

    def get_value(self, setting: GraphvizSettings):
        return self.__settings.get(setting).value

    def hook(self, event_type, context):
        if event_type == EventTypes.CliStart:
            self.do_start()

        if self.enabled:
            if event_type == EventTypes.CliExit:
                self.do_exit()

            if event_type == EventTypes.BlueprintLoaded:
                self.do_load(context)

    def do_start(self):
        path = self.get_value(GraphvizSettings.Svg)
        if path in ["", None]:
            self.enabled = False
            logger.warn(f'Extension "{self.name}" disabled due to missing values')
        else:
            self.enabled = True

    def _write_svg(self, path):
        graph = copy.deepcopy(self._graph)
        graph.format = "svg"
        graph.render(outfile=path)

    def do_exit(self):
        outpath = resolve_str_or_path(self.get_value(GraphvizSettings.Svg))
        self._write_svg(path=outpath)
        click.echo(f"{OutputPrefixes.Good} Writing graph SVG to {outpath.as_posix()}")

    def do_load(self, context):
        blueprint: Blueprint = context.blueprint
        groups = {}
        for variant in blueprint.variants:
            for group in variant.groups:
                groups.setdefault(group.name, set()).add(variant.tid)

        graph = graphviz.Digraph("graph", comment=blueprint.name, engine="neato")
        graph.attr(overlap="false")
        graph.attr(outputorder="edgesfirst")

        def standard_node(name, color, **kwargs):
            graph.node(name, style="filled", fillcolor=color, fontcolor="white", fontname="times bold", **kwargs)

        standard_node(blueprint.name, "purple", pos="0,0")
        for group_name, tids in groups.items():
            standard_node(group_name, "red")
            graph.edge(blueprint.name, group_name)
            for tid in tids:
                standard_node(tid, "blue")
                graph.edge(group_name, tid)
        self._graph = graph


hook = GraphvizHook()
