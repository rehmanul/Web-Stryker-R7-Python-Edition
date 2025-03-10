#!/usr/bin/env python
"""
Setup script for Web Stryker R7 Python Edition
"""
from setuptools import setup, find_packages

setup(
    name="webstryker",
    version="1.0.0",
    description="Web Stryker R7 - Advanced Web Data Extraction Tool",
    author="Web Stryker Team",
    packages=find_packages(),
    install_requires=[
        "requests>=2.26.0",
        "beautifulsoup4>=4.10.0",
        "flask>=2.0.1",
        "sqlite3>=3.35.0",
        "aiohttp>=3.8.1",
        "pandas>=1.3.3",
        "pillow>=8.3.2",
        "openai>=0.27.0",
        "google-api-python-client>=2.31.0",
        "werkzeug>=2.0.1",
        "marshmallow>=3.13.0",
        "tqdm>=4.62.3",
    ],
    entry_points={
        "console_scripts": [
            "webstryker=webstryker.main:main_entry",
        ],
    },
    python_requires=">=3.7",
    include_package_data=True,
    package_data={
        "webstryker": [
            "templates/*.html",
            "static/css/*.css",
            "static/js/*.js",
            "static/img/*.png",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
