"""A made-up drive, for screenshots and for trying the app without scanning anything."""

from __future__ import annotations

import math
import random

from .model import DirNode, ScanTree, aggregate

KB = 1024
MB = 1024 * KB
GB = 1024 * MB


def _files(rng: random.Random, folder: DirNode, pattern: str, count: int,
           smallest: float, largest: float, *, online_only: bool = False) -> None:
    """Add ``count`` files named from ``pattern``, sizes spread log-evenly between the bounds."""
    low, high = math.log(smallest), math.log(largest)
    for i in range(1, count + 1):
        folder.add_file(pattern.format(i), int(math.exp(rng.uniform(low, high))), online_only=online_only)


def build_demo_tree(seed: int = 4) -> ScanTree:
    rng = random.Random(seed)
    root = DirNode("D:\\")

    home = root.add_dir("Users").add_dir("Alex")

    videos = home.add_dir("Videos")
    _files(rng, videos.add_dir("Holiday 2025"), "VID_2025_{:04d}.mp4", 14, 900 * MB, 3.8 * GB)
    _files(rng, videos.add_dir("Family"), "family_{:03d}.mov", 9, 400 * MB, 2.2 * GB)
    _files(rng, videos.add_dir("Screen recordings"), "Recording {:03d}.mkv", 22, 60 * MB, 900 * MB)

    pictures = home.add_dir("Pictures")
    camera = pictures.add_dir("Camera Roll")
    for year in (2022, 2023, 2024, 2025):
        _files(rng, camera.add_dir(str(year)), "IMG_{:04d}.jpg", rng.randint(250, 600), 2.5 * MB, 7 * MB)
    _files(rng, pictures.add_dir("RAW"), "DSC{:05d}.cr3", 380, 22 * MB, 34 * MB)
    _files(rng, pictures.add_dir("Edits"), "edit_{:03d}.psd", 30, 80 * MB, 400 * MB)

    music = home.add_dir("Music")
    for artist in ("The Lanterns", "Mira Sol", "Northbound", "Cass & Co", "Static Bloom", "Orla Reyes"):
        artist_dir = music.add_dir(artist)
        for album in range(1, rng.randint(2, 4)):
            ext = "flac" if rng.random() < 0.4 else "mp3"
            _files(rng, artist_dir.add_dir(f"Album {album}"), "{:02d} Track." + ext,
                   rng.randint(9, 14), 4 * MB if ext == "mp3" else 25 * MB, 11 * MB if ext == "mp3" else 60 * MB)

    documents = home.add_dir("Documents")
    work = documents.add_dir("Work")
    _files(rng, work, "Report {:03d}.pdf", 120, 200 * KB, 12 * MB)
    _files(rng, work, "Budget {:03d}.xlsx", 40, 50 * KB, 3 * MB)
    _files(rng, work, "Slides {:03d}.pptx", 25, 2 * MB, 90 * MB)
    _files(rng, documents.add_dir("Scans"), "scan_{:04d}.pdf", 300, 300 * KB, 4 * MB)
    _files(rng, documents.add_dir("Taxes"), "tax_{:04d}.pdf", 60, 100 * KB, 2 * MB)

    downloads = home.add_dir("Downloads")
    downloads.add_file("ubuntu-24.04-desktop-amd64.iso", int(5.7 * GB))
    downloads.add_file("TestMachine.vhdx", 18 * GB)
    _files(rng, downloads, "setup_{:02d}.exe", 12, 40 * MB, 600 * MB)
    _files(rng, downloads, "archive_{:02d}.zip", 18, 10 * MB, 1.2 * GB)

    projects = home.add_dir("Projects")
    website = projects.add_dir("website")
    modules = website.add_dir("node_modules")
    for i in range(1, 161):
        _files(rng, modules.add_dir(f"package-{i:03d}"), "file{:03d}.js", rng.randint(5, 60), 1 * KB, 90 * KB)
    _files(rng, website.add_dir("src"), "component{:02d}.tsx", 40, 2 * KB, 30 * KB)
    game = projects.add_dir("game-prototype")
    _files(rng, game.add_dir("Textures"), "tex_{:03d}.png", 220, 1 * MB, 16 * MB)
    _files(rng, game.add_dir("Audio"), "sfx_{:03d}.wav", 140, 200 * KB, 9 * MB)
    _files(rng, game.add_dir("Builds"), "build_{:02d}.zip", 6, 300 * MB, 900 * MB)
    data = projects.add_dir("data")
    _files(rng, data, "measurements_{:02d}.csv", 10, 50 * MB, 700 * MB)
    _files(rng, data, "cache_{:02d}.parquet", 8, 100 * MB, 1.5 * GB)

    local = home.add_dir("AppData").add_dir("Local")
    _files(rng, local.add_dir("Temp"), "tmp{:05d}.tmp", 900, 4 * KB, 20 * MB)
    _files(rng, local.add_dir("Browser").add_dir("Cache"), "f_{:06x}", 1500, 2 * KB, 600 * KB)

    onedrive = home.add_dir("OneDrive")
    _files(rng, onedrive.add_dir("Shared photos"), "photo_{:04d}.jpg", 400, 2 * MB, 6 * MB, online_only=True)
    _files(rng, onedrive.add_dir("Archive"), "backup_{:02d}.zip", 10, 300 * MB, 2 * GB, online_only=True)
    _files(rng, onedrive.add_dir("Notes"), "note_{:03d}.docx", 60, 20 * KB, 2 * MB)

    common = root.add_dir("Games").add_dir("Steam").add_dir("steamapps").add_dir("common")
    skyward = common.add_dir("Skyward Isles")
    _files(rng, skyward.add_dir("Content").add_dir("Paks"), "pakchunk{:02d}-Windows.pak", 9, 1.5 * GB, 9 * GB)
    _files(rng, skyward.add_dir("Binaries"), "module{:02d}.dll", 30, 2 * MB, 80 * MB)
    skyward.add_file("SkywardIsles.exe", 140 * MB)
    neon = common.add_dir("Neon Drift")
    _files(rng, neon.add_dir("Data"), "level{:02d}.bundle", 40, 80 * MB, 700 * MB)
    _files(rng, neon.add_dir("Movies"), "intro_{:02d}.webm", 6, 200 * MB, 1.1 * GB)
    _files(rng, common.add_dir("Tiny Farm"), "assets{:02d}.pak", 6, 100 * MB, 600 * MB)

    program_files = root.add_dir("Program Files")
    for name in ("PhotoStudio", "OfficeSuite", "Blender Foundation", "Code Editor", "Video Converter"):
        app = program_files.add_dir(name)
        _files(rng, app, "lib{:03d}.dll", rng.randint(40, 160), 200 * KB, 60 * MB)
        _files(rng, app.add_dir("resources"), "res{:03d}.dat", rng.randint(10, 40), 1 * MB, 120 * MB)

    windows = root.add_dir("Windows")
    _files(rng, windows.add_dir("System32"), "sys{:04d}.dll", 1400, 20 * KB, 9 * MB)
    _files(rng, windows.add_dir("WinSxS"), "component{:04d}.dll", 1600, 10 * KB, 6 * MB)
    _files(rng, windows.add_dir("Installer"), "{:08x}.msi", 40, 2 * MB, 300 * MB)
    _files(rng, windows.add_dir("Fonts"), "font{:03d}.ttf", 300, 50 * KB, 3 * MB)

    root.add_file("pagefile.sys", 12 * GB)
    root.add_file("hiberfil.sys", int(6.4 * GB))

    aggregate(root)
    total = 931 * GB
    used = root.size + 41 * GB  # some space no scan can see: system files, restore points
    return ScanTree(root, "D:\\", elapsed=4.7, skipped_links=3, disk=(total, used, total - used))
