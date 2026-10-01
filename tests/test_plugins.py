"""Plugin registry, discovery, hot reload, templates and contracts."""

import pytest
from calflab.plugins import PLUGIN_TYPES, PluginWatcher, register, registry
from calflab.plugins.contracts import check_plugin
from calflab.plugins.discovery import load_file
from calflab.plugins.templates import create, render
from calflab.plugins.types import FitnessTerm


def _all_plugins():
    from calflab.plugins import load_plugins

    load_plugins()
    return registry.everything()


@pytest.mark.parametrize("cls", _all_plugins(), ids=lambda c: f"{c.plugin_type}:{c.key}")
def test_every_registered_plugin_honours_its_contract(cls):
    assert check_plugin(cls) == []


def test_every_plugin_type_has_at_least_one_plugin():
    for ptype in PLUGIN_TYPES:
        assert registry.all(ptype), f"no {ptype} plugin registered"


@pytest.mark.parametrize("ptype", PLUGIN_TYPES)
def test_new_plugin_template_passes_contract(ptype, tmp_path):
    name = f"tmpl_{ptype}"
    plugin_path, test_path = create(ptype, name, tmp_path / "plugins", tmp_path / "tests")
    assert test_path.is_file()
    try:
        assert load_file(plugin_path) is None
        cls = registry.get(ptype, name)
        assert check_plugin(cls) == []
        desc = cls.describe()
        assert desc["key"] == name and "fields" in desc["schema"]
    finally:
        registry.unregister_module(f"calflab_user_plugins.{name}")


def test_template_rejects_bad_input(tmp_path):
    with pytest.raises(ValueError):
        render("no_such_type", "x")
    with pytest.raises(ValueError):
        render("controller", "Bad-Name")
    create("controller", "dup", tmp_path, tmp_path)
    with pytest.raises(FileExistsError):
        create("controller", "dup", tmp_path, tmp_path)


def test_contract_catches_a_bad_plugin():
    class Bad(FitnessTerm):
        key = "bad_term"
        label = ""

        def evaluate(self, metrics, context):
            return "not a number"

    problems = check_plugin(Bad)
    assert any("label" in p for p in problems)


def test_duplicate_key_from_another_module_is_rejected():
    cls = type("Clash", (FitnessTerm,), {"key": "forward_speed", "label": "x", "__module__": "elsewhere"})
    with pytest.raises(ValueError, match="already registered"):
        register(cls)


def test_hot_reload_picks_up_changes_and_removals(tmp_path):
    src, _ = render("fitness_term", "hot_term")
    path = tmp_path / "hot_term.py"
    changed: list[list[str]] = []
    watcher = PluginWatcher(tmp_path, on_change=changed.append)
    try:
        path.write_text(src, encoding="utf-8")
        assert watcher.poll() == [str(path)]
        assert registry.get("fitness_term", "hot_term").label == "Hot term"

        import os

        path.write_text(src.replace('label = "Hot term"', 'label = "Hotter"'), encoding="utf-8")
        os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 5))
        watcher.poll()
        assert registry.get("fitness_term", "hot_term").label == "Hotter"

        path.write_text("this is not python (", encoding="utf-8")
        os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 10))
        watcher.poll()
        assert not registry.has("fitness_term", "hot_term")
        assert str(path) in registry.errors

        path.unlink()
        watcher.poll()
        assert str(path) not in registry.errors
        assert len(changed) == 4
    finally:
        registry.unregister_module("calflab_user_plugins.hot_term")
        registry.errors.pop(str(path), None)
