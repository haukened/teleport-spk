#!/usr/bin/env python3

import argparse
import datetime
import git
import logging
import os
import psutil
import requests
import shutil
import subprocess
import tempfile
import urllib.request, json

from halo import Halo
from tqdm import tqdm
from typing import List

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Github URLs
BRANCHES_URL_FORMAT = "https://api.github.com/repos/{}/{}/branches"
REPO_URL_FORMAT = "https://github.com/{}/{}.git"

# SynologyOpenSource github repo
SYNO_GITHUB_USER="SynologyOpenSource"
SYNO_GITHUB_REPO="pkgscripts-ng"
PKGSCRIPTS_REPO_URL = REPO_URL_FORMAT.format(SYNO_GITHUB_USER, SYNO_GITHUB_REPO)
DSM_BRANCHES_API_URL = BRANCHES_URL_FORMAT.format(SYNO_GITHUB_USER, SYNO_GITHUB_REPO)

# teleport github repo
TELEPORT_GITHUB_USER = "gravitational"
TELEPORT_GITHUB_REPO = "teleport"
TELEPORT_REPO_URL = REPO_URL_FORMAT.format(TELEPORT_GITHUB_REPO, TELEPORT_GITHUB_REPO)
TELEPORT_BRANCHES_URL = BRANCHES_URL_FORMAT.format(TELEPORT_GITHUB_REPO, TELEPORT_GITHUB_REPO)

# DSM processor families
SUPPORTED_PLATFORMS=[
    "bromolow", 
    "avoton", 
    "alpine", 
    "braswell", 
    "apollolake", 
    "grantley", 
    "alpine4k", 
    "monaco", 
    "broadwell", 
    "broadwellntbap", 
    "kvmx64", 
    "kvmcloud", 
    "armada38x", 
    "denverton", 
    "rtd1296", 
    "broadwellnk", 
    "armada37xx", 
    "purley", 
    "geminilake", 
    "v1000", 
    "epyc7002", 
    "r1000", 
    "broadwellnkv2", 
    "rtd1619b"
]

# fetch the current versions of DSM supported by synology
SUPPORTED_VERSIONS=[]
with urllib.request.urlopen(DSM_BRANCHES_API_URL) as url:
    try:
        data = json.load(url)
    except:
        print("Unable to load DSM versions from github")
        exit(1)
    for item in data:
        version = str(item['name']).strip("DSM")
        if version != "master":
            SUPPORTED_VERSIONS.append(version)

# parse the command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--dsm-version", help="select the target version of DSM software", choices=SUPPORTED_VERSIONS, default=SUPPORTED_VERSIONS[-1])
parser.add_argument("--processor", help="select the target processor family", choices=SUPPORTED_PLATFORMS, required=True)
parser.add_argument("--cache-path", help="the path where downloads are cached", default="/var/cache/syno-build")
parser.add_argument("--nocache", help="dont use cached files, always download", action="store_true")
args = parser.parse_args()

# gets the list of files from synology's autoupdate API
def get_syno_filelist(version: str, processor: str) -> List[str]:
    SYNO_URL = "https://dataautoupdate7.synology.com/toolchain/v1/get_download_list/toolkit/{}/{}".format(version, processor)
    with urllib.request.urlopen(SYNO_URL) as url:
        try:
            data = json.load(url)
            return data['fileList']
        except:
            print("Unable to fetch toolkit download links")
            exit(1)

# actually downloads a file
def download_file(url: str, filename: str):
    baseName = os.path.basename(url)
    chunkSize = 1024
    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        pbar = tqdm(desc="downloading {}".format(baseName), unit="B", unit_scale=True, total=int(r.headers['Content-Length']), leave=False)
        for chunk in r.iter_content(chunk_size=chunkSize):
            pbar.update(len(chunk))
            f.write(chunk)
        pbar.clear()
    logging.info('downloaded {}'.format(baseName))

# gets a file from the cache, or downloads it
def get_file(url: str, filename: str):
    baseName = os.path.basename(filename)
    if args.nocache:
        download_file(url, filename)
    else:
        # send a head request to get the file eTag header
        cache_filename = requests.head(url).headers['etag'].strip("\"") + ".txz"
        cache_filepath = os.path.join(args.cache_path, cache_filename)
        if os.path.isfile(cache_filepath):
            # the file is already in the cache
            logging.info("found {} in {}".format(baseName, args.cache_path))
        else:
            logging.info("{} not found in cache, downloading".format(baseName))
            # download the file to the cache
            download_file(url, cache_filepath)
        # copy the file to the destination
        shutil.copyfile(cache_filepath, filename)            
    
if os.geteuid() != 0:
    print("Please run this script with sudo, due to permissions required by the synology build system.")
    exit(1)

# log the arguments
logging.info("building teleport for DSM {} on {}".format(args.dsm_version, args.processor))

# ensure the cache folder exists
if not os.path.exists(args.cache_path):
    logging.info("Creating cache folder {}".format(args.cache_path))
    os.makedirs(args.cache_path)

# create a temporary build directory
# this uses context so the directory will be deleted when the context is exited
with tempfile.TemporaryDirectory(prefix="syno-build-") as build_directory:
    logging.info("building in {}".format(build_directory))

    # create the required directories
    toolkit_path = os.path.join(build_directory, "scripts")
    os.makedirs(toolkit_path)
    tarball_path = os.path.join(build_directory, "toolkit_tarballs")
    os.makedirs(tarball_path)
    src_path = os.path.join(build_directory, "source")
    os.makedirs(src_path)

    # clone the toolchain
    try:
        syno_repo = git.Repo.clone_from(PKGSCRIPTS_REPO_URL, toolkit_path)
    except:
        logging.error("unable to clone github repo {}".format(PKGSCRIPTS_REPO_URL))
        exit(2)

    # switch to the DSM branch
    logging.info("cloning toolkit int build directory")
    syno_repo.git.checkout("DSM{}".format(args.dsm_version))

    # download the toolkit tarballs
    filesToDownload = get_syno_filelist(args.dsm_version, "base") + get_syno_filelist(args.dsm_version, args.processor)
    for url in filesToDownload:
        filename = str(url).split('/')[-1]
        filepath = os.path.join(tarball_path, filename)
        get_file(url, filepath)
    
    # set up the environment by calling EnvDeploy
    # this will mount proc in the dev folder, preventing deletion, it will need to be unmounted after
    logging.info("deploying build environment")
    with Halo(text="{} JOKE     Playing some pong while tar files extract".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")), spinner="pong", placement="right"):
        with open("envdeploy.log", "wb") as logfile:
            deploy_script = os.path.join(toolkit_path, "EnvDeploy")
            subprocess.run([deploy_script, "-D", "-v", args.dsm_version, "-p", args.processor], check=True, stdout=logfile, stderr=logfile)
    
    ##############################################
    ##### all the build logic should go here #####
    ##############################################
    
    # first we need to check out the teleport github repo

    ##############################################
    ############## End Build Logic ###############
    ##############################################

    # This should be last before the temp directory is deleted
    # we need to detect and unmount the proc mount
    parts = psutil.disk_partitions(all=True)
    for part in parts:
        if "syno-build" in part.mountpoint:
            logging.info("unmounting chroot from {}".format(part.mountpoint))
            subprocess.run(["umount", part.mountpoint], check=True)