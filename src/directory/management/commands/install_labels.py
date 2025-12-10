from django import setup as setup_django
from django.core.management.base import BaseCommand
import importlib.util
import sys
from neomodel import install_all_labels, install_labels

class Command(BaseCommand):
    help = 'Install labels and constraints for your neo4j database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--class',
            type=str,
            help="Class name"
        )
        parser.add_argument(
            '--module',
            type=str,
            help="python module"
        )
    def handle(self, *args, **options):
        setup_django()
        class_name = options["class"]
        module_name = options["module"]
        if class_name and module_name:
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
    
            the_class = getattr(module, class_name)
    
            if class_name and module_name and the_class:
                install_labels(
                    the_class,
                    quiet=False,
                    stdout=self.stdout
                )
        else:
            install_all_labels(
                stdout=self.stdout
            )