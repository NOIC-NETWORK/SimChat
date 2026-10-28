"""`chat.mode` 钩子注册表。"""

from collections import OrderedDict


class ModeRegistry(object):
    def __init__(self):
        self._modes = OrderedDict()

    def register(self, mod_id, spec):
        mode_id = spec.get("id")
        if not mode_id:
            raise ValueError("模式缺少 id")
        if mode_id in self._modes:
            existing = self._modes[mode_id]
            raise ValueError(
                "模式 id 冲突: %s（已由 %s 注册）" % (mode_id, existing.get("mod_id"))
            )
        entry = dict(spec)
        entry["mod_id"] = mod_id
        self._modes[mode_id] = entry
        return entry

    def remove_mod(self, mod_id):
        for mode_id in [key for key, value in self._modes.items() if value.get("mod_id") == mod_id]:
            self._modes.pop(mode_id, None)

    def get(self, mode_id):
        return self._modes.get(mode_id)

    def list_modes(self):
        return sorted(
            (dict(value) for value in self._modes.values()),
            key=lambda item: (item.get("order", 100), item.get("id", "")),
        )

    def has(self, mode_id):
        return mode_id in self._modes

    def __len__(self):
        return len(self._modes)
