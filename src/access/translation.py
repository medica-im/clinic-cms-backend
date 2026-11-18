from modeltranslation.translator import translator, TranslationOptions

from access.models import Role

class RoleTranslationOptions(TranslationOptions):
    # description only. `label` was translated here too, which is what created
    # label_fr/label_en — a second bilingual catalogue of the five role names
    # that nothing served and that drifted from the frontend's. Re-adding it
    # would recreate those columns on the next makemigrations.
    fields = ('description',)


translator.register(Role, RoleTranslationOptions)