# -*- coding: utf-8 -*-

'''
Модуль для работы с API "Госзатрат".
Отбор контрактов по ИНН поставщика,
проверка наличия среди продуктов в этих контрактах тех, которые имеют отношение к СМИ.
Отношение определяется по кодам продукции ОКПД или ОКПД2.
Предварительно составленные значения кодов загружаются из файлов JSON.
Документация API "Госзатрат": https://github.com/idalab/clearspending-examples/wiki
'''

import requests  # для запросов к API
import json  # для загрузки файлов JSON
import math  # опционально - для вычисления количества полученных страниц
import time  # опционально - чтобы измерять время работы скрипта


# ПОЛЯ, ИСПОЛЬЗУЕМЫЕ В СЛОВАРЯХ ДЛЯ КАЖДОГО ПОДХОДЯЩЕГО КОНТРАКТА
CONTRACT_URL = 'contract_url'  # URL карточки контракта на "Госзатратах"
CONTRACT_PRICE = 'contract_price'  # Общая сумма контракта
PRODUCT_DESCRIPTION = 'product_description'  # Описание конкретного продукта
PRODUCT_PRICE = 'product_price'  # Сумма по позиции конкретного продукта
NUM_PRODUCTS = 'num_products'  # Число продуктов в контракте


def load_json(source):
    '''
    Загрузить файл JSON в виде списка или словаря
    '''
    with open(source, 'r') as handler:
        return json.load(handler)


def get_supplier_name(inn):
    '''
    Проверить наличие ИНН поставщика в базе.
    При наличии вернуть имя поставщика.
    В случае отсутствия - уведомление об отсутствии поставщика в базе.
    '''
    target_url = 'http://openapi.clearspending.ru/restapi/v3/suppliers/get/?inn={}'.format(inn)  # адрес API запроса
    # try - except на случай непредвиденных обстоятельств.
    try:
        response = requests.get(target_url)  # запрос с заданным ИНН поставщика
        if response.status_code == 404:
            # Если указанного ИНН нет в базе, то запрос возвращает статус 404
            # print(u'Не могу найти поставщика с ИНН {}'.format(inn))
            return u'Не могу найти поставщика с ИНН {}'.format(inn)
        data = response.json()  # Преобразовать полученные данные в словарь
        name = data['suppliers']['data'][0].get('allNames', [u'Имярек'])[0]  # Получить первый вариант наименования
        # print(name)
        return name
    # Если что-то не срабатывает, распечатывается ошибка.
    except Exception as e:
        print(e)


def get_contracts_by_inn(inn):
    '''
    Получить все контракты поставщика по ИНН.
    Возвращает tuple в формате:
    (НАЗВАНИЕ_ПОСТАВЩИКА, ЧИСЛО_ЕГО_КОНТРАКТОВ, СПИСОК_СЛОВАРЕЙ_ПО_РЕЛЕВАНТНЫМ_КОНТРАКТАМ)
    '''
    supplier_name = get_supplier_name(inn)  # Проверить наличие / получить наименование поставщика

    if supplier_name is None:
        # Возвращает None в случае except => см. распечатанную ошибку
        return u'Что-то пошло не так'

    elif u'Не могу найти поставщика с ИНН' in supplier_name:
        # Указывает на отсутствие поставщика с таким ИНН в базе "Госзатрат"
        return supplier_name

    # Адрес запроса к API "Госзатрат"
    # Фильтрация контрактов по ИНН поставщика, сортировка по дате подписания: сначала последние
    url = 'http://openapi.clearspending.ru/restapi/v3/contracts/select/?supplierinn={}&sort=-signDate'.format(inn)
    data = requests.get(url).json()['contracts']  # Преобразование данных запроса в словарь
    total = data['total']  # Общее число найденных контрактов
    per_page = data['perpage']  # Сколько контрактов выводится на страницу
    num_pages = math.ceil(total / per_page)  # Число страниц выдачи
    # print(total)

    all_media_contracts = list()  # Инициализация списка, куда будут собираться контракты, касающиеся СМИ
    for page in range(1, int(num_pages) + 1):
        # Цикл проходит по всем страницам с полученными контрактами
        target_url = url + '&page={}'.format(page)  # Вставка в запрос номера нужной страницы
        contracts = requests.get(target_url).json()['contracts']['data']  # Список всех контрактов на этой странице
        all_media_contracts.extend(filter_media_contracts(contracts))  # Добавить в список подходящие контракты
    # print(len(all_media_contracts))
    return supplier_name, total, all_media_contracts


def filter_media_contracts(contracts):
    '''
    Проверить контракты поставщика на наличие в них продуктов, касающихся СМИ, в пределах одной страницы.
    Возвращает список словарей с информацией о релевантных контрактов.
    В случае отсутствия релевантных контрактов возвращает пустой список.
    '''
    okpd_ref = load_json('okpd_smi.json')  # Справочник с кодами ОКПД
    okpd2_ref = load_json('okpd2_smi.json')  # Справочник с кодами ОКПД2

    media_contracts = list()  # Инициализация списка, в который будут собираться релевантные контракты
    clearspending_base = 'https://clearspending.ru/contract/'  # Общее для всех начало URL карточек контрактов на ГЗ
    for contract in contracts:
        products = contract['products']  # список всех продуктов в контракте
        for product in products:
            okpd = product.get('OKPD', {}).get('code')  # Если поля с ОКПД нет, значение None
            okpd2 = product.get('OKPD2', {}).get('code')  # Если поля с ОКПД2 нет, значение None

            if okpd in okpd_ref or okpd2 in okpd2_ref:
                # При наличии ОКПД или ОКПД2 в заданных списках добавляем контракт в список релевантных
                contract_price = contract.get('price', '-')
                product_price = product.get('sum', '-')
                product_description = product.get('name', '-')
                regnum = contract['regNum']  # Реестровый номер контракта нужен для создания URL его карточки
                contract_url = clearspending_base + regnum
                num_products = len(products)
                media_contracts.append({CONTRACT_URL: contract_url,
                                        CONTRACT_PRICE: contract_price,
                                        PRODUCT_DESCRIPTION: product_description,
                                        PRODUCT_PRICE: product_price,
                                        NUM_PRODUCTS: num_products})
                # При получении первого релевантного продукта прерываем проверку продуктов этого контракта
                # и переходим к следующему.
                break
    return media_contracts


if __name__ == '__main__':
    # get_contracts_by_inn('6450614330')
    # filter_media_contracts()
    # get_contracts_by_inn('7717039300')
    # get_contracts_by_inn('7704552473')
    # get_contracts_by_inn('7703191457')

    # start = time.time()
    # get_contracts_by_inn('7705035012') # Мосэнерго
    # get_contracts_by_inn('7701371574') # РЖД
    # get_contracts_by_inn('7826159654')  # РЖД-Партнер.РУ ИА
    # stop = time.time()
    # running_time =stop - start
    # print('running time:', running_time)
    get_supplier_name(7826159654)