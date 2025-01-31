import json
import logging
from typing import Optional, List
from urllib import parse

import requests
# from kivy.logger import Logger

from utils import Song

Logger = logging.getLogger('gtplayer')

class Response:

    def __init__(self, req, trigger, context: dict = None):
        from kivy.clock import Clock
        self.response = None
        self.is_finished = False
        self.status_code = 0
        self.trigger = trigger
        self.context = context if context else {}
        self.req = req
        self.event = Clock.schedule_interval(lambda *args: self.on_finish(
            self.req, self.req.result), .1)
        Logger.debug('Response: Response object with trigger %s', trigger)

    def on_finish(self, req, result=None, progress=None):
        self.is_finished = req.is_finished
        self.status_code = req.resp_status
        if not self.is_finished:
            return
        Logger.debug('%s status code', req.resp_status)
        if self.status_code == 200:
            if req.url.startswith(Sender.API_ROOT + 'recommendations'):
                self.response = [Song(**x) for x in result['recommendations']]
            else:
                self.response = result
        else:
            Logger.debug('Failed request with payload: %s', result)

        if self.trigger is not None:
            Logger.debug('Trigger: Activated for %s, Payload: %s',
                         req.url,
                         self.response)
            self.event.cancel()
            if not self.trigger.is_triggered:
                self.trigger()

    def __repr__(self):
        return (f'Response(is_finished={self.is_finished},'
                f' trigger={True if self.trigger else False}')


class Sender:
    """Sends HTTP requests."""
    # Create a persistent requests connection
    API_ROOT = 'https://geniust-recommender.herokuapp.com/'
    AUTH_HEADER = {
        "Authorization": ("Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
                          "eyJ1c2VyIjoiZ2VuaXVzdG11c2ljcGxheWVyIiwiZ3Jvd"
                          "XAiOiJkZWZhdWx0In0.IDXKFocZM4JpDzE3xsO-M-iCOk"
                          "4LhAZjr7IxR0OJz4U")
    }

    def __init__(
        self,
        timeout=5,
        sleep_time=0.2,
        retries=0
    ):
        self.session = requests.Session()
        self.headers = {
            'application': 'GeniusT Music Player',
        }
        self.session.headers.update(self.headers)
        self.timeout = timeout
        self.sleep_time = sleep_time
        self.retries = retries

    def make_request(
        self,
        path,
        params=None,
        method='GET',
        web=False,
        trigger=None,
        async_request: bool = True,
        api: bool = True,
        timeout=None,
        raw=False,
        use_requests=False,
        **kwargs
    ):
        """Makes a request to Genius."""
        if api:
            url = self.API_ROOT + path
            if "headers" in kwargs:
                headers = kwargs["headers"]
                headers.update(self.AUTH_HEADER)
            else:
                headers = self.AUTH_HEADER
        else:
            headers = kwargs.get("headers")
            url = path

        params = params if params else {}
        use_requests = use_requests or trigger is None
        if use_requests:
            req = self.session.get(url, headers=headers, params=params)
            response = req.content if raw else req.json()
            Logger.debug("RESPONSE: %s - URL %s - Payload: %s",
                         req.status_code,
                         req.url,
                         response if not raw else "Bytes")
        else:
            from kivy.network.urlrequest import UrlRequest

            for key in list(params):
                if params[key] is None:
                    params.pop(key)
            url_parse = parse.urlparse(url)
            query = url_parse.query
            url_dict = dict(parse.parse_qsl(query))
            url_dict.update(params)
            url_new_query = parse.urlencode(url_dict)
            url_parse = url_parse._replace(query=url_new_query)
            new_url = parse.urlunparse(url_parse)

            # Make the request
            if headers is not None:
                req_headers = self.headers.copy()
                req_headers.update(headers)
            else:
                req_headers = self.headers
            req = UrlRequest(new_url,
                             req_headers=req_headers,
                             timeout=timeout or self.timeout,
                             debug=True,
                             verify=False,
                             )
            response = Response(req, trigger, context=kwargs)
            response.is_finished = req.is_finished

            # Enforce rate limiting
            # time.sleep(self.sleep_time)

            if not async_request:
                req.wait()

        return response


class API():
    def __init__(self):
        timeout = 7
        retries = 2
        sleep_time = 0.2
        self.sender = Sender(sleep_time=sleep_time, timeout=timeout, retries=retries)

    def get_genres(
        self,
        age: Optional[int] = None,
        trigger=None,
        async_request: bool = True
    ) -> List[str]:
        params = {'age': age}
        res = self.sender.make_request(
            'genres',
            params=params,
            trigger=trigger,
            async_request=async_request
        )

        return res

    def get_recommendations(
        self,
        genres: List[str],
        artists: Optional[List[str]] = None,
        song_type='any_file',
        trigger=None,
        async_request: bool = True,
        timeout=None,
    ) -> List[str]:
        params = {
            'genres': ','.join(genres),
        }
        if artists:
            params['artists'] = ','.join(artists)
        params['song_type'] = 'preview'  # song_type
        res = self.sender.make_request(
            'recommendations',
            params=params,
            trigger=trigger,
            async_request=async_request,
            timeout=timeout,
        )
        if isinstance(res, Response):
            return res
        else:
            return [Song(**x) for x in res['recommendations']]

    def search_artists(
        self,
        artist: str,
        trigger=None,
        async_request: bool = True
    ) -> List[str]:
        params = {'q': artist}
        res = self.sender.make_request(
            'search/artists',
            params=params,
            trigger=trigger,
            async_request=async_request
        )

        return [x["name"] for x in res["hits"]]

    def download_preview(
        self,
        song: Song,
        trigger=None,
        async_request: bool = True
    ) -> List[str]:
        res = self.sender.make_request(
            song.preview_url,
            trigger=trigger,
            async_request=async_request,
            api=False,
            raw=True
        )

        return res

    def get_preferences(
        self,
        code: str,
        platform: str,
        trigger=None,
        async_request: bool = True
    ) -> List[str]:
        params = {f'{platform}_code': code}
        res = self.sender.make_request(
            'https://geniust.herokuapp.com/preferences',
            params=params,
            trigger=trigger,
            async_request=async_request,
            api=False
        )

        return res["preferences"]
