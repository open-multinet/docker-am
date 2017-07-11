"""
gcf_docker_plugin
==================

"""

__title__ = 'gcf_docker_plugin'
__version__ = '1.0'
__author__ = 'David Margery <david.margery@inria.fr>, Arthur Garnier <arthur.garnier@inria.fr>, Wim Van de Meerssche <wim.vandemeerssche@ugent.be>'
__license__ = 'MIT License'
__copyright__ = 'Copyright 2015 - contributor(s): David Margery, Arthur Garnier, Wim Van de Meerssche'

from .testbed import DockerAggregateManager
from dockercontainer import DockerContainer
from dockermaster import DockerMaster
from gcf_to_docker import DockerManager
from extendedresource import ExtendedResource
