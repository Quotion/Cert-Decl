import os
import sys
import time
import json
import urllib3
import requests

import pandas as pd

from tqdm import tqdm
from datetime import datetime, timedelta


# отключаем варнинги от библиотеки
urllib3.disable_warnings()


def main(type_requested_data: str, date_start_end: int, date_end_of: int, termination: str):

    login_url = "https://pub.fsa.gov.ru/login"

    certificates_url = "https://pub.fsa.gov.ru/api/v1/rss/common/certificates/get"
    one_certificates_url = "https://pub.fsa.gov.ru/api/v1/rss/common/certificates/{}"
    certificates_url_view = "https://pub.fsa.gov.ru/rss/certificate/view/{}/baseInfo"

    declarations_url = "https://pub.fsa.gov.ru/api/v1/rds/common/declarations/get"
    one_declarations_url = "https://pub.fsa.gov.ru/api/v1/rds/common/declarations/{}"
    declarations_url_view = "https://pub.fsa.gov.ru/rds/declaration/view/{}/common"

    # Запрашиваем токен аутентификации, без которого просматривать какую-либо 
    # информацию будет не возможно
    response: requests.Response = requests.post(login_url, 
                             data="{\"username\": \"anonymous\", \"password\": \"hrgesf7HDR67Bd\"}", 
                             verify=False)

    # Если токен не получен, выход из программы
    if response.status_code != 200:
        print("Доступ к API не предоставлен... Попробуйте позже.")
        os.system('pause')
        exit()
    else:
        token: str = response.headers.get('Authorization')
    
    # Указываем токен авторизации
    headers: dict = {'Authorization': token,
                     'Content-Type': 'application/json'}

    # Интервал окончания действия документов
    date_start = datetime.now() + timedelta(days=date_start_end)
    date_end = datetime.now() + timedelta(days=date_end_of)

    if termination.lower() == "y":
        status = [14, 15]
    else:
        status = [6]

    params: dict = {
        "size":1000000,
        "page":0,
        "filter":{
            "status": status,
            "idCertObjectType":[3],
            "regDate":{
                "minDate":"",
                "maxDate":""},
            "endDate":{
                "minDate":date_start.strftime("%Y-%m-%d"),
                "maxDate":date_end.strftime("%Y-%m-%d")},
            "columnsSearch":[]
        }
    }

    response: requests.Response = requests.post(certificates_url if type_requested_data.lower() == 'c' else declarations_url, 
                                                data=json.dumps(params), 
                                                headers=headers, 
                                                verify=False)
    data = response.json()
    given_data: pd.DataFrame = pd.DataFrame(columns=['Рег. номер', 'Продукция', 'Статус', 'Дата формирования отчета', 
                                                     'Дата окончания', 'E-mail заявителя', 'Ссылка', 'Изготовитель'])

    for row, i in zip(data['items'],tqdm(range(len(data['items'])), desc='Чтение JSON...')):
        response_data: requests.Response = requests.get(
            one_certificates_url.format(row['id']) if type_requested_data.lower() == 'c' else one_declarations_url.format(row['id']), 
            headers=headers, verify=False)
        
        if response_data.status_code != 200:
            for j in range(10):
                time.sleep(2)
                response_data: requests.Response = requests.get(
                one_certificates_url.format(row['id']) if type_requested_data.lower() == 'c' else one_declarations_url.format(row['id']), 
                headers=headers, verify=False)
                if response_data.status_code != 200:
                    if j == 9:
                        name_file = "certificates_" if type_requested_data.lower() == 'c' else "declarations_"
                        print('\nОшибка получения данных после 9 ошибок (Ошибка сервера: 503)\nСоздаем бэкап.')
                        given_data.to_excel(f"data/backup_{name_file}{date_start.strftime('%Y-%m-%d')}_{date_end.strftime('%Y-%m-%d')}_{datetime.now().strftime('%d_%m_%Y_%H_%M')}.xlsx", 
                                            engine='xlsxwriter')
                        print("Бэкап сделан. Попробуйте повторить попытку получения сертификатов/деклараций позже...")
                        os.system('pause')
                        exit()
                    else:
                        print(f"\nОшибка. #{response_data.status_code}.\n{j}-ая попытка получения данных.")
                        continue
                elif j > 0:
                    print(f"\nУспешная попыка получения данных со {j}-го раза. Продолжаем...")
                    break
        
        r_data = response_data.json()

        email = [kr['value'] for kr in r_data['applicant']['contacts'] if kr['idContactType'] == 4]
        if email:
            email = email[0]
        else:
            email = ''

        if str(r_data['idStatus']) == '14':
            status = 'Прекращен'
        elif str(r_data['idStatus']) == '6':
            status = 'Действует'
        elif str(r_data['idStatus']) == '11':
            status = 'Недействителен'
        elif str(r_data['idStatus']) == '15':
            status = 'Приостановлен'
        else:
            status = r_data['idStatus']

        given_data.loc[i] = (
            r_data['number'], 
            r_data['product']['fullName'], 
            status, 
            datetime.now().strftime("%d.%m.%Y"), 
            r_data['certEndDate'] if type_requested_data.lower() == 'c' else r_data['declEndDate'], 
            email, 
            certificates_url_view.format(r_data['idCertificate']) if type_requested_data.lower() == 'c' else declarations_url_view.format(r_data['idDeclaration']),
            row['applicantName'])

        name_file = "certificates_" if type_requested_data.lower() == 'c' else "declarations_"

    given_data.to_excel(f"data/{name_file}{date_start.strftime('%Y-%m-%d')}_{date_end.strftime('%Y-%m-%d')}_{datetime.now().strftime('%d-%m-%Y-%H-%M')}.xlsx", 
                        engine='xlsxwriter')


if __name__ == "__main__":
    arguments: list = sys.argv

    if len(arguments) > 1:
        if '-type' in arguments and len(arguments) != arguments.index('-type') + 1:
            type_requested_data: str = arguments[arguments.index('-type') + 1]
            if type_requested_data.lower() != 'c' and type_requested_data.lower() != 'd' \
                and type_requested_data.lower() != 'с' and type_requested_data.lower() != 'в':
                print("Выберите один из типов: «D» или «C»!")
                os.system('pause')
                exit()
            elif type_requested_data.lower() == 'c' or type_requested_data.lower() == 'с':
                type_requested_data = 'c'
            elif type_requested_data.lower() == 'd' or type_requested_data.lower() == 'в':
                type_requested_data = 'd'

        if '-start' in arguments and len(arguments) != arguments.index('-start') + 1:
            start_date = arguments[arguments.index('-start') + 1]
            if not start_date.isdigit():
                print("Вы ввели не число. Пожалуйста укажите числовое значение!")
                os.system('pause')
                exit()
            elif int(start_date) < 1:
                print("Вы ввели отрицательное число! Зачем, а главнео почему?")
                os.system('pause')
                exit()

        if '-end' in arguments and len(arguments) != arguments.index('-end') + 1:
            end_date = arguments[arguments.index('-start') + 1]
            if not end_date.isdigit():
                print("Вы ввели не число. Пожалуйста укажите числовое значение!")
                os.system('pause')
                exit()
            elif int(end_date) < 1:
                print("Вы ввели отрицательное число! Зачем, а главнео почему?")
                os.system('pause')
                exit()

        if '-stoped' in arguments and len(arguments) != arguments.index('-stoped') + 1:
            termination = arguments[arguments.index('-stoped') + 1]
            if termination.lower() != 'y' and termination.lower() != 'n' \
                and termination.lower() != 'н' and termination.lower() != 'т':
                print("Выберите один из типов: «Y» или «N»!")
                os.system('pause')
                exit()
            elif termination.lower() == 'y' or termination.lower() == 'н':
                termination = 'y'
            elif termination.lower() == 'n' or termination.lower() == 'т':
                termination = 'n'

    else:
        type_requested_data: str = str(input("Сертификаты - «C» или Декларации - «D»: "))
        if type_requested_data.lower() != 'c' and type_requested_data.lower() != 'd' \
            and type_requested_data.lower() != 'с' and type_requested_data.lower() != 'в':
            print("Выберите один из типов: «D» или «C»!")
            os.system('pause')
            exit()
        elif type_requested_data.lower() == 'c' or type_requested_data.lower() == 'с':
            type_requested_data = 'c'
        elif type_requested_data.lower() == 'd' or type_requested_data.lower() == 'в':
            type_requested_data = 'd'

        start_date: str = str(input("Введите начальный интервал окончания действия: "))
        if not start_date.isdigit():
            print("Вы ввели не число. Пожалуйста укажите числовое значение!")
            os.system('pause')
            exit()
        elif int(start_date) < 1:
            print("Вы ввели отрицательное число! Зачем, а главнео почему?")
            os.system('pause')
            exit()


        end_date: str = str(input("Введите конечный интервал окончания действия: "))
        if not end_date.isdigit():
            print("Вы ввели не число. Пожалуйста укажите числовое значение!")
            os.system('pause')
            exit()
        
        termination: str = str(input('Прекращенн «Y» или нет «N»: '))
        if termination.lower() != 'y' and termination.lower() != 'n' \
            and termination.lower() != 'н' and termination.lower() != 'т':
            print("Выберите один из типов: «Y» или «N»!")
            os.system('pause')
            exit()
        elif termination.lower() == 'y' or termination.lower() == 'н':
            termination = 'y'
        elif termination.lower() == 'n' or termination.lower() == 'т':
            termination = 'n'

    print(type_requested_data, int(start_date), int(end_date), termination)
    main(type_requested_data, int(start_date), int(end_date), termination)