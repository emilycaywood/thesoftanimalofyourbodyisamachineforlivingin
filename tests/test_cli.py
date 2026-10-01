"""CLI helpers: where environments live."""

from pathlib import Path

from calflab.cli import webenv


def test_cloud_synced_folders_are_detected(monkeypatch, tmp_path):
    monkeypatch.delenv("OneDriveConsumer", raising=False)
    monkeypatch.delenv("OneDriveCommercial", raising=False)
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    assert webenv.cloud_synced(tmp_path / "OneDrive" / "Documents" / "CALFLAB" / "web") == "OneDrive"
    assert webenv.cloud_synced(Path("G:/My Drive/THESIS/repo/web")) == "Google Drive"
    assert webenv.cloud_synced(tmp_path / "Dropbox" / "repo") == "Dropbox"
    assert webenv.cloud_synced(tmp_path / "dev" / "calflab") is None


def test_node_modules_stay_out_of_synced_folders(monkeypatch, tmp_path):
    monkeypatch.delenv("CALFLAB_WEB_IN_TREE", raising=False)
    monkeypatch.setattr(webenv, "web_dir", lambda: tmp_path / "OneDrive" / "repo" / "web")
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    assert webenv.in_tree() is False
    monkeypatch.setenv("CALFLAB_WEB_IN_TREE", "1")
    assert webenv.in_tree() is True
