from libmm.extension import AbstractUserHook, EventTypes, TestCaseRenderContext


"""
This extension will modify exported Variants to comply with test case structure expected by VECTR
"""


class VectrHook(AbstractUserHook):
    def __init__(self):
        self.enabled = True
        self._id_key_name = "x_vectr_id"

    @property
    def name(self):
        return "vectr"

    @property
    def settings(self):
        return []

    def hook(self, event_type, context):
        if self.enabled:
            if event_type == EventTypes.TestCaseRender:
                self.do_render(context)

    @staticmethod
    def do_render(context: TestCaseRenderContext):
        """
        Modifies the exported Variant in the following ways:
        - add the "x_vectr_id" metadata header
        - add the "isv" static metdata header
        - alias the "tools" metadata to "x_tools"
        - alias the "references" metadata to "x_references"
        """
        variant = context.variant
        variant["metadata"]["x_vectr_id"] = variant["metadata"]["id"]
        variant["metadata"]["isv"] = 1
        if "tools" in variant["metadata"] and len(variant["metadata"]["tools"]) > 0:
            variant["metadata"]["x_tools"] = variant["metadata"]["tools"]
            del variant["metadata"]["tools"]
        if "references" in variant["metadata"] and len(variant["metadata"]["references"]) > 0:
            variant["metadata"]["x_references"] = variant["metadata"]["references"]
            del variant["metadata"]["references"]


hook = VectrHook()
