PublicHolidayZones = {
        'alsace-moselle': 'Alsace-Moselle',
        'guadeloupe': 'Guadeloupe',
        'guyane': 'Guyane',
        'la-reunion': 'La Réunion',
        'martinique': 'Martinique',
        'mayotte': 'Mayotte',
        'metropole': 'Métropole',
        'nouvelle-caledonie': 'Nouvelle-Calédonie',
        'polynesie-francaise': 'Polynésie française',
        'saint-barthelemy': 'Saint-Barthélemy',
        'saint-martin': 'Saint-Martin',
        'saint-pierre-et-miquelon': 'Saint-Pierre-et-Miquelon',
        'wallis-et-futuna': 'Wallis-et-Futuna'
}

departements_by_holiday_zone = {
    'alsace-moselle': [
        '67', '68', '57'
    ],
    'guadeloupe': [
        '971'
    ],
    'guyane': [
        '973'
    ],
    'la-reunion': [
        '974'
    ],
    'martinique': [
        '972'
    ],
    'mayotte': [
        '976'
    ],
    'metropole': [
        '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
        '13', '14', '15', '16', '17', '18', '19', '2A', '2B', '21', '22', '23',
        '24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34',
        '35', '36', '37', '38', '39', '40', '41', '42', '43', '44', '45',
        '46', '47', '48', '49', '50', '51', '52', '53', '54', '55', '56',
        '57', '58', '59', '60', '61', '62', '63', '64', '65', '66', '67',
        '68', '69', '70', '71', '72', '73', '74', '75', '76', '77', '78',
        '79', '80', '81', '82', '83', '84', '85', '86', '87', '88', '89',
        '90', '91', '92', '93', '94', '95'
    ],
    'nouvelle-caledonie': [
        '988'
    ],
    'polynesie-francaise': [
        '987'
    ],
    'saint-barthelemy': [
        '977'
    ],
    'saint-martin': [
        '978'
    ],
    'saint-pierre-et-miquelon': [
        '975'
    ],
    'wallis-et-futuna': [
        '986'
    ]
}
import logging
from django.core.management.base import BaseCommand, CommandError
import neomodel
from directory.models.graph import PublicHolidayZone, DepartmentOfFrance

logger = logging.getLogger(__name__)

class Command(BaseCommand):
        help = 'Create Public Holiday Zones and link them to departments.'

        def warn(self, message):
                self.stdout.write(
                        self.style.WARNING(message)
                )

        def handle(self, *args, **options):
                created = 0
                skipped = 0
                for name, label in PublicHolidayZones.items():
                        try:
                                # check if node exists
                                PublicHolidayZone.nodes.get(name=name)
                                skipped += 1
                        except neomodel.DoesNotExist:
                                # create node
                                PublicHolidayZone(name=name, label=label).save()
                                created += 1
                self.stdout.write(
                        self.style.SUCCESS(
                                f"PublicHolidayZone nodes created: {created}, already existed: {skipped}"
                        )
                )
                # Build mapping for specific zones (exclude metropole default)
                for dept in DepartmentOfFrance.nodes.all():
                    code = getattr(dept, 'code', None)
                    if not code:
                        error_message = f"Department {dept} has no code"
                        logger.error(error_message)
                        raise CommandError(error_message)
                    zone = None
                    for zone_name, dept_codes in departements_by_holiday_zone.items():
                        if code in dept_codes:
                            zone = zone_name
                            break
                    try:
                        zone_node = PublicHolidayZone.nodes.get(name=zone)
                    except neomodel.DoesNotExist:
                        logger.warning(f"PublicHolidayZone {zone} does not exist")
                        raise CommandError(f"PublicHolidayZone {zone} does not exist")
                    try:
                        if not dept.public_holiday_zone.is_connected(dept):
                            dept.public_holiday_zone.connect(zone_node)
                            linked += 1
                        else:
                            already_linked += 1
                    except Exception as e:
                        logger.error(f"Error linking department {dept} to zone {zone}: {e}")
                        raise CommandError(f"Error linking department {dept} to zone {zone}: {e}")
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Departments linked: {linked} out of a total of {len(DepartmentOfFrance.nodes.all())}, already linked: {already_linked}"
                    )
                )



