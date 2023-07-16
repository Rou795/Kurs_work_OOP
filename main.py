import os
from urllib.parse import urlencode
import urllib.request
import requests
import json
from datetime import datetime
from tqdm import tqdm
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# Описание класса пользователя


class Client:
    api_base_url_vk = 'https://api.vk.com/method/'
    api_base_url_ya = 'https://cloud-api.yandex.net:443'

    def __init__(self, token_vk, user_id, token_ya):
        self.token_vk = token_vk
        self.user_id = user_id
        self.token_ya = token_ya
        self.g_auth = GoogleAuth()
        self.g_auth.LocalWebserverAuth()
        self.drive = GoogleDrive(self.g_auth)

# Метод загрузки фото из VK

    def get_profile_photos(self, album_id='profile'):
        params = {'access_token': self.token_vk,
                  'v': '5.131',
                  'extended': '1'
                  }
        params.update({'user_id': self.user_id, 'album_id': album_id})
        response = requests.get(f'{self.api_base_url_vk}/photos.get?{urlencode(params)}')
        if 200 <= response.status_code < 300:
            print(f'Доступ к файлам есть, формируем список для резервного копирования')
            data = response.json()
            with open('response.json', 'w') as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
            photo_list = []
            likes_str = ''
            for idx, item in enumerate(data['response']['items']):
                photo_list.append({'date': datetime.fromtimestamp(item['date']),
                                   'likes': item['likes']['count']})
                likes_str += str(item['likes']['count']) + ' '
                max_type = max_size(item['sizes'])
                for size in item['sizes']:
                    if size['type'] == max_type:
                        photo_list[idx]['url'] = size['url']
                        photo_list[idx]['size'] = size['type']
                sort_photo_list = sorted(photo_list, key=lambda x: x['likes'])
            for photo in sort_photo_list:
                if likes_str.count(str(photo['likes'])) > 1:
                    photo['file_name'] = f'{photo["likes"]}_{photo["date"].strftime("%m_%d_%y_%H_%M_%S")}.jpg'
                else:
                    photo['file_name'] = f'{photo["likes"]}.jpg'
        return sort_photo_list

# Метод загрузки файлов в Google Drive
    def upload_gd(self, upload_list):
        file_list = self.drive.ListFile({'q': "'root' in parents and trashed=false"}).GetList()
        file_id = ''
        for file in file_list:
            if file['title'] == 'photo_VK':
                file_id = file['id']
        if file_id == '':
            file_id = self.make_folder_gd()
        for file in tqdm(upload_list):
            params = {'title': file['file_name'],
                      'parents': [{'id': file_id}]}
            file_cont = self.drive.CreateFile({'mimeTipe': 'jpg', 'parents': [{"kind": "drive#fileLink",
                                                                              "id": file_id}]})
            urllib.request.urlretrieve(file['url'], file['file_name'])
            file_cont.SetContentFile(file['file_name'])
            file_cont.Upload()
        print(f'Резервное копирование на Google Drive прошло успешно')
# Метод для проверки наличия папки, яндекс

    def remove_after_all(self, upload_list):
        for file in upload_list:
            os.remove(file['file_name'])

    def check_folder_ya(self):
        headers = {'Authorization': self.token_ya}
        url = self.api_base_url_ya + '/v1/disk/resources'
        param = {'path': '/фото_вк'}
        response = requests.get(url, headers=headers, params=param)
        return response.status_code

# Метод для создания папки. Добавлено ожидание, если папка создаётся не сразу

    def make_folder_ya(self):
        headers = {'Authorization': self.token_ya}
        url = self.api_base_url_ya + '/v1/disk/resources'
        param = {'path': '/фото_вк'}
        response = requests.put(url, headers=headers, params=param)
        return response.status_code
# Метод для создания папки у Google Drive

    def make_folder_gd(self):
        file_cont = self.drive.CreateFile({'title': 'фото_вк', 'mimeType': 'application/vnd.google-apps.folder'})
        file_cont.Upload()
        return file_cont['id']

# Метод для проверки фото, которые уже были загружены в данную папку

    def photos_in_folder_ya(self):
        name_in_fold = []
        headers = {'Authorization': self.token_ya}
        url = self.api_base_url_ya + '/v1/disk/resources'
        param = {'path': '/фото_вк',
                 'limit': 1000000000000}
        response = requests.get(url, headers=headers, params=param)
        if 200 <= response.status_code < 300:
            data = response.json()
            for item in data['_embedded']['items']:
                name_in_fold.append(item['name'])
            return name_in_fold

# метод для связки проверки сузествования папки, её создания и загрузки файлов
    def upload_ya(self, file_list):
        result = self.check_folder_ya()
        if 200 <= result < 300:
            print(f'Папка есть, приступаем к резервному копированию')
            self.only_upload_ya(file_list)
        elif result == 404:
            response = self.make_folder_ya()
            if 200 <= response < 300:
                self.only_upload_ya(file_list)
        elif 400 <= result < 500:
            print(f'Проблема с программой')
        elif result >= 500:
            print(f'Проблема на стороне Яндекса')

# Метод для загрузки файлов в диск
    def only_upload_ya(self, file_list):
        name_in_fold = self.photos_in_folder_ya()
        headers = {'Authorization': self.token_ya}
        response_list = []
        if name_in_fold:
            for item in tqdm(file_list):
                if not(item['file_name'] in name_in_fold):
                    print(item['file_name'])
                    param = {'path': f'/фото_вк/{item["file_name"]}',
                             'url': item['url']}
                    url = self.api_base_url_ya + '/v1/disk/resources/upload'
                    response = requests.post(url, headers=headers, params=param)
                    response_list.append({'file_name': item['file_name'], 'code': response.status_code})
            bad_list = []
            for file in response_list:
                if not(200 <= file['code'] < 300):
                    bad_list.append(file['file_name'])
            if bad_list:
                print(f'При резервном копировании на Яндекс Диск произошла ошибка со следующими файлами:', end=' ')
                for file in bad_list:
                    print(file, end=' ')
            else:
                print(f'Резервное копирование на Яндекс Диск прошло успешно')
        else:
            for item in tqdm(file_list):
                param = {'path': f'/фото_вк/{item["file_name"]}',
                         'url': item['url']}
                url = self.api_base_url_ya + '/v1/disk/resources/upload'
                response = requests.post(url, headers=headers, params=param)
                response_list.append({'file_name': item['file_name'], 'code': response.status_code})
            bad_list = []
            for file in response_list:
                if not (200 <= file['code'] < 300):
                    bad_list.append(file['file_name'])
            if bad_list:
                print(f'При резервном копировании на Яндекс Диск произошла ошибка со следующими файлами:', end=' ')
                for file in bad_list:
                    print(file, end=' ')
            else:
                print(f'Резервное копирование на Яндекс Диск прошло успешно')


def max_size(items: list):
    max_value = 0
    max_type = ''
    for item in items:
        if item['height'] * item['width'] >= max_value:
            max_value = item['height'] * item['width']
            max_type = item['type']
    return str(max_type)

token_vk = input(f'Введите токен для VK: ').strip()

token_ya = input(f'Введите токен для Яндекс Диска: ').strip()


user = Client(token_vk, 36356648, token_ya)
photo_list = user.get_profile_photos()

json_data = []
upload_data = []

for item in photo_list:
    json_data.append({'file_name': item['file_name'],
                      'size': item['size']})
    upload_data.append({'file_name': item['file_name'],
                        'url': item['url']})
print(len(photo_list))

with open('files_list.json', 'w') as f:
    json.dump(json_data, f, ensure_ascii=False, indent=2)

user.upload_ya(upload_data)
user.upload_gd(upload_data)
user.remove_after_all(upload_data)
