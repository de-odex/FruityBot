from setuptools import setup, find_packages
import sys

long_description = None

def read():
    with open('README.md') as f:
        long_description = f.read()

setup(
    name='FruityBot',
    version='0.5',
    packages=find_packages(),
    url='https://github.com/de-odex/FruityBot',
    license='MIT',
    author='deodex',
    author_email='',
    description='An osu! irc bot for sub-mode performance point calculation',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Framework :: Twisted',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Games/Entertainment',
    ],
    install_requires=['twisted', 'slider', 'colorama', 'requests'],
    python_requires="3.6.2",
    dependency_links=['https://github.com/llllllllll/slider/tarball/master#egg=0.1.0'],
    entry_points={
        'console_scripts': [
            'bot = fruity.bot:main',
        ]
    }

)
