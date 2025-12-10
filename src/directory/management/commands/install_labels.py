from django import setup as setup_django
from django.core.management.base import BaseCommand
import importlib.util
import sys
import os
from neomodel.scripts import neomodel_install_labels


class Command(BaseCommand):
    help = 'Install labels and constraints for your neo4j database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            type=str,
            help="python module"
        )
    def handle(self, *args, **options):
        setup_django()
        module_name = options["module"]
        if module_name:
            if module_name in sys.modules:
                print(f"{module_name!r} already in sys.modules")
                module = sys.modules[module_name]
            elif (spec := importlib.util.find_spec(module_name)) is not None:
                # If you chose to perform the actual import ...
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                print(f"{module_name!r} has been imported")
            else:
                print(f"can't find the {module_name!r} module")
            os.popen(f"neomodel_install_labels {module_name}")