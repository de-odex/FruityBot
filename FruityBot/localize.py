import logging

import i18n
import pycountry

logger = logging.getLogger(__name__)


class LocaleException(Exception):
    pass


languages = [lang for lang in pycountry.languages]
alpha_2_langs = [i.alpha_2 for i in languages if hasattr(i, 'alpha_2')]


def tl(tl_namespace: str, locale: str):
    locale = 'en' if not locale else locale
    i18n.set('locale', locale)
    i18n.set('fallback', 'en')
    result = i18n.t(tl_namespace)
    if locale and locale.lower() not in alpha_2_langs:
        raise LocaleException("Invalid locale")
    if result == tl_namespace:
        raise LocaleException("No translation in any locale")
    return result


def load_locales():
    for directory in i18n.config.get('load_path'):
        for locale in alpha_2_langs:
            try:
                i18n.resource_loader.load_directory(directory, locale)
            except i18n.resource_loader.I18nFileLoadError as e:
                if "defined" not in str(e):
                    logger.warning(f"File not loaded; {e}")


def get_locales():
    return list(i18n.translations.container.keys())
