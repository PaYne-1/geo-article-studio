"""Single-attempt OpenAI-compatible image transport; no implicit paid retries."""
from __future__ import annotations

import base64
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import tempfile
import urllib.parse
import uuid
import warnings

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat


class ProviderError(RuntimeError):
    """Safe public error: remote bodies, URLs and credentials are never included."""
    def __init__(self, code: str, status_unknown: bool = False, retryable: bool = False):
        self.code = code
        self.status_unknown = status_unknown
        self.retryable = retryable
        super().__init__(code)

    def as_dict(self):
        return {'code': self.code, 'status_unknown': self.status_unknown, 'retryable': self.retryable}


def validate_image(path, dimensions=None, image_format=None):
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ProviderError('invalid_image')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as im:
                width, height = im.size
                actual_format = im.format.lower()
                if getattr(im, 'n_frames', 1) != 1:
                    raise ProviderError('animated_image_unsupported')
                im.verify()
            with Image.open(path) as im:
                im.load()
        if actual_format not in {'png', 'jpeg', 'webp'}:
            raise ProviderError('format_unsupported')
        if dimensions is not None and [width, height] != list(dimensions):
            raise ProviderError('dimensions_mismatch')
        expected = (image_format or path.suffix.lstrip('.')).lower().replace('jpg', 'jpeg')
        if expected and actual_format != expected:
            raise ProviderError('format_mismatch')
        from .storage import file_hash
        return {'path': str(path.resolve()), 'hash': file_hash(path), 'format': actual_format,
                'width': width, 'height': height, 'bytes': path.stat().st_size}
    except ProviderError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ProviderError('invalid_image') from None


def normalize_image_canvas(path, dimensions, image_format, padding_color=(245,245,245)):
    """Preserve the complete returned image and pad it to the requested canvas."""
    path=Path(path);meta=validate_image(path,image_format=image_format)
    target=tuple(dimensions)
    if (meta['width'],meta['height'])==target:return None
    fmt=image_format.lower().replace('jpg','jpeg')
    try:
        with Image.open(path) as source:
            source.load()
            contained=ImageOps.contain(source.convert('RGBA'),target,Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',target,(*padding_color,255))
        left=(target[0]-contained.width)//2;top=(target[1]-contained.height)//2
        canvas.alpha_composite(contained,(left,top))
        output=canvas.convert('RGB')
        output.save(path,format={'png':'PNG','jpeg':'JPEG','webp':'WEBP'}[fmt])
    except (OSError,ValueError,KeyError):raise ProviderError('dimension_normalization_failed') from None
    return {'method':'contain_pad','original_dimensions':[meta['width'],meta['height']],
            'output_dimensions':list(dimensions),'padding_color':list(padding_color)}


def composite_product(background_path, product_path, output_path, *, placement='lower_center',
                      width_fraction=.72, bottom_margin=24):
    """Integrate an approved cutout without generatively altering its structure."""
    if placement not in {'lower_left','lower_center','lower_right'}:raise ValueError('invalid_product_placement')
    if not isinstance(width_fraction,(int,float)) or isinstance(width_fraction,bool) or not .2<=width_fraction<=.9:
        raise ValueError('invalid_product_scale')
    if type(bottom_margin) is not int or bottom_margin<0:raise ValueError('invalid_product_margin')
    background_path=Path(background_path);product_path=Path(product_path);output_path=Path(output_path)
    if output_path.exists() or output_path.is_symlink():raise ValueError('output_exists')
    with Image.open(background_path) as raw_background, Image.open(product_path) as raw_product:
        background=raw_background.convert('RGBA')
        if 'A' not in raw_product.getbands():raise ValueError('product_alpha_required')
        product=raw_product.convert('RGBA')
        # Ignore near-transparent export noise when finding the product bounds,
        # while retaining every original pixel inside the selected rectangle.
        bbox=product.getchannel('A').point(lambda value:255 if value>=32 else 0).getbbox()
        if not bbox:raise ValueError('empty_product_alpha')
        product=product.crop(bbox)
        max_width=max(1,round(background.width*width_fraction));max_height=max(1,background.height-bottom_margin)
        ratio=min(max_width/product.width,max_height/product.height)
        size=(max(1,round(product.width*ratio)),max(1,round(product.height*ratio)))
        product=product.resize(size,Image.Resampling.LANCZOS)
        margin=max(0,round(background.width*.035))
        x={'lower_left':margin,'lower_center':(background.width-product.width)//2,
           'lower_right':background.width-product.width-margin}[placement]
        x=max(0,min(x,background.width-product.width));y=max(0,background.height-product.height-bottom_margin)
        region=background.crop((x,y,x+product.width,y+product.height)).convert('RGB')
        local_rgb=tuple(round(value) for value in ImageStat.Stat(region).mean[:3])
        alpha=product.getchannel('A')
        product_rgb=product.convert('RGB')
        product_mean=ImageStat.Stat(product_rgb,mask=alpha).mean
        local_luma=sum(local_rgb)/3;product_luma=max(1,sum(product_mean[:3])/3)
        brightness=max(.88,min(1.12,local_luma/product_luma))
        product_rgb=ImageEnhance.Brightness(product_rgb).enhance(brightness)
        tint=Image.new('RGB',product.size,local_rgb)
        product_rgb=Image.blend(product_rgb,tint,.06)
        product=product_rgb.convert('RGBA');product.putalpha(alpha)
        shadow=Image.new('RGBA',background.size,(0,0,0,0));draw=ImageDraw.Draw(shadow)
        shadow_box=(x+round(product.width*.06),y+product.height-round(product.height*.045),
                    x+product.width-round(product.width*.06),min(background.height,y+product.height+round(product.height*.07)))
        draw.ellipse(shadow_box,fill=(12,12,12,72))
        shadow=shadow.filter(ImageFilter.GaussianBlur(max(2,round(product.width*.025))))
        background.alpha_composite(shadow)
        background.alpha_composite(product,(x,y))
        output_path.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.composite-',suffix=output_path.suffix,dir=output_path.parent);temp=Path(name)
        try:
            with os.fdopen(fd,'wb') as handle:
                background.convert('RGB').save(handle,format='PNG' if output_path.suffix.lower()=='.png' else 'JPEG')
                handle.flush();os.fsync(handle.fileno())
            os.link(temp,output_path)
        finally:temp.unlink(missing_ok=True)
    return {'method':'approved_product_alpha_composite','source_bbox':list(bbox),
            'output_dimensions':[background.width,background.height],'placement':placement,
            'width_fraction':width_fraction,'bottom_margin':bottom_margin,
            'placed_box':[x,y,x+product.width,y+product.height],
            'light_integration':{'method':'bounded_color_match_contact_shadow','local_rgb':list(local_rgb),
                                 'brightness_factor':round(brightness,4),'tint_strength':.06,
                                 'shadow_box':list(shadow_box)}}


class ImageProvider:
    ALLOWED = {'adapter', 'base_url', 'model', 'api_key_env', 'auth_type',
               'supports_references', 'max_reference_images', 'allowed_local_hosts',
               'timeout_seconds', 'max_response_bytes', 'max_image_bytes',
               'max_reference_bytes', 'output_formats', 'extra_parameters',
               'extra_parameter_allowlist', 'idempotency_header', 'response_format',
               'send_output_format', 'send_response_format', 'edit_image_field', 'generation_endpoint', 'edit_endpoint'}

    def __init__(self, config):
        self.config = dict(config)

    def check(self):
        c = self.config
        errors = []
        scalar_fields=('base_url','model','api_key_env','adapter','auth_type','idempotency_header',
                       'response_format','edit_image_field','generation_endpoint','edit_endpoint')
        if any(name in c and c[name] is not None and not isinstance(c[name],str) for name in scalar_fields):
            return {'ok':False,'errors':['invalid_config_type'],'network_verified':False,'capabilities':{}}
        if set(c) - self.ALLOWED: errors.append('unknown_parameters')
        if c.get('adapter') != 'openai_compatible': errors.append('adapter_unsupported')
        for name in ('base_url', 'model', 'api_key_env'):
            if not isinstance(c.get(name), str) or not c[name].strip(): errors.append('missing_' + name)
        try:
            base=urllib.parse.urlsplit(c.get('base_url') or '')
            if base.scheme not in {'http','https'} or not base.hostname or base.query or base.fragment or base.username or base.password:
                errors.append('invalid_base_url')
            _=base.port
        except ValueError: errors.append('invalid_base_url')
        local=c.get('allowed_local_hosts',[])
        if not isinstance(local,list) or any(not isinstance(host,str) or not re.fullmatch(r'[a-zA-Z0-9.:-]+',host) for host in local):
            errors.append('invalid_local_allowlist')
        if c.get('idempotency_header') not in {None,'Idempotency-Key','X-Idempotency-Key'}:
            errors.append('invalid_idempotency_header')
        for name in ('send_output_format','send_response_format'):
            if name in c and type(c[name]) is not bool: errors.append('invalid_'+name)
        if c.get('auth_type', 'bearer') not in {'bearer', 'none'}: errors.append('auth_unsupported')
        if c.get('auth_type', 'bearer') == 'bearer' and not os.environ.get(c.get('api_key_env') or ''):
            errors.append('missing_api_key')
        if type(c.get('supports_references')) is not bool: errors.append('reference_capability_unconfigured')
        if type(c.get('max_reference_images')) is not int or c.get('max_reference_images', -1) < 0:
            errors.append('invalid_reference_limit')
        for name, default in [('timeout_seconds',60),('max_response_bytes',32*1024*1024),('max_image_bytes',20*1024*1024),('max_reference_bytes',20*1024*1024)]:
            v=c.get(name,default)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v <= 0: errors.append('invalid_'+name)
        formats = c.get('output_formats', [])
        if not isinstance(formats,list) or not formats or any(f not in {'png','jpeg','webp'} for f in formats): errors.append('invalid_output_formats')
        extra=c.get('extra_parameters',{})
        allowed=c.get('extra_parameter_allowlist',[])
        if not isinstance(allowed,list) or any(not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*',key) for key in allowed):
            errors.append('invalid_extra_parameter_allowlist')
            allowed=[]
        if not isinstance(extra,dict) or set(extra)-set(allowed):
            errors.append('extra_parameters_not_allowed')
        if isinstance(extra,dict) and any(not isinstance(v,(str,int,float,bool)) or isinstance(v,float) and not math.isfinite(v) for v in extra.values()):
            errors.append('invalid_extra_parameter_value')
        if isinstance(extra,dict) and set(extra)&{'model','prompt','n','size','image','image[]','response_format','output_format','stream'}:
            errors.append('reserved_extra_parameter')
        if c.get('response_format','b64_json') not in {'b64_json','url'}: errors.append('response_format_unsupported')
        if c.get('edit_image_field','image') != 'image': errors.append('image_field_unsupported')
        for name, default in [('generation_endpoint','/images/generations'),('edit_endpoint','/images/edits')]:
            value = c.get(name,default)
            if not isinstance(value,str) or not value.startswith('/') or '?' in value or '#' in value or '..' in value or '://' in value:
                errors.append('invalid_endpoint')
        return {'ok': not errors, 'errors': errors, 'network_verified': False,
                'capabilities': {'references': c.get('supports_references',False),
                    'max_reference_images':c.get('max_reference_images',0), 'query': False,
                    'idempotency': bool(c.get('idempotency_header')), 'declared_not_remotely_verified':True}}

    def query(self, request_id):
        return {'supported': False, 'request_id': request_id, 'status': 'UNKNOWN',
                'code': 'query_unsupported', 'message': '此同步协议未定义任务查询；须人工核实结果和收费状态。'}

    def _address(self, url):
        try:
            parsed=urllib.parse.urlsplit(url)
            host=parsed.hostname
            if parsed.scheme not in {'http','https'} or not host or parsed.username or parsed.password or parsed.fragment:
                raise ProviderError('unsafe_url')
            allowed=host in self.config.get('allowed_local_hosts',[])
            if parsed.scheme != 'https' and not allowed: raise ProviderError('unsafe_url')
            port=parsed.port or (443 if parsed.scheme=='https' else 80)
            addresses=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
            ips=list(dict.fromkeys(info[4][0] for info in addresses))
            if not ips or (not allowed and any(not ipaddress.ip_address(ip).is_global for ip in ips)):
                raise ProviderError('unsafe_url')
            return parsed, ips[0], port
        except ProviderError: raise
        except (ValueError,OSError): raise ProviderError('unsafe_url') from None

    def _request(self, url, method, body=None, headers=None, limit=None):
        # Resolve once, validate every answer, and connect to that exact IP to avoid DNS rebinding.
        parsed, address, port=self._address(url)
        timeout=self.config.get('timeout_seconds',60)
        conn = (http.client.HTTPSConnection(parsed.hostname,port,timeout=timeout,context=ssl.create_default_context())
                if parsed.scheme=='https' else http.client.HTTPConnection(parsed.hostname,port,timeout=timeout))
        conn._create_connection=lambda target, timeout, source_address=None: socket.create_connection((address,port),timeout,source_address)
        limit=int(limit or self.config.get('max_response_bytes',32*1024*1024))
        started=False
        try:
            conn.connect()
            started=True
            conn.request(method,urllib.parse.urlunsplit(('', '', parsed.path or '/',parsed.query,'')),body,headers or {})
            response=conn.getresponse()
            if response.status in {301,302,303,307,308}:
                if method != 'GET': raise ProviderError('generation_redirect_rejected',status_unknown=True)
                return response.status, response.getheader('Location'), b''
            if response.status in {401,403}: raise ProviderError('authentication_failed')
            if response.status == 429: raise ProviderError('rate_limited',retryable=True)
            if response.status >= 500: raise ProviderError('server_error',status_unknown=method=='POST')
            if not 200 <= response.status < 300: raise ProviderError('request_rejected')
            length=response.getheader('Content-Length')
            if length is not None and int(length)>limit: raise ProviderError('response_too_large')
            data=response.read(limit+1)
            if len(data)>limit: raise ProviderError('response_too_large')
            return response.status, None, data
        except ProviderError: raise
        except (TimeoutError,socket.timeout):
            raise ProviderError('request_timeout',status_unknown=started and method=='POST') from None
        except (OSError,http.client.HTTPException,ValueError):
            raise ProviderError('transport_error',status_unknown=started and method=='POST') from None
        finally: conn.close()

    def _download(self,url):
        for _ in range(4):
            # Deliberately no API authorization, including on same-origin downloads.
            status, location, data=self._request(url,'GET',limit=self.config.get('max_image_bytes',20*1024*1024))
            if 200<=status<300: return data
            if not location: raise ProviderError('invalid_redirect')
            url=urllib.parse.urljoin(url,location)
        raise ProviderError('too_many_redirects')

    def generate(self,prompt,reference_paths,output_path,*,dimensions,image_format,request_id):
        c=self.config
        check=self.check()
        if not check['ok']: raise ProviderError(check['errors'][0])
        if not isinstance(prompt,str) or not prompt.strip(): raise ProviderError('invalid_prompt')
        if not isinstance(request_id,str) or not request_id or any(ord(x)<32 or ord(x)>126 for x in request_id):
            raise ProviderError('invalid_request_id')
        if not isinstance(dimensions,(list,tuple)) or len(dimensions)!=2 or any(type(n) is not int or n<=0 for n in dimensions):
            raise ProviderError('invalid_dimensions')
        fmt=image_format.lower().replace('jpg','jpeg')
        if fmt not in c['output_formats']: raise ProviderError('format_unsupported')
        output_path=Path(output_path)
        if output_path.exists() or output_path.is_symlink(): raise ProviderError('output_exists')
        if output_path.suffix.lower().lstrip('.').replace('jpg','jpeg') != fmt: raise ProviderError('format_mismatch')
        if reference_paths and not c['supports_references']: raise ProviderError('references_unsupported')
        if len(reference_paths)>c['max_reference_images']: raise ProviderError('too_many_references')
        references=[]; blobs=[]
        for ref in reference_paths:
            try:
                ref=Path(ref)
                if ref.stat().st_size>c.get('max_reference_bytes',20*1024*1024): raise ProviderError('reference_too_large')
                meta=validate_image(ref)
                blob=ref.read_bytes()
                if hashlib.sha256(blob).hexdigest()!=meta['hash']: raise ProviderError('reference_changed')
                references.append(meta); blobs.append(blob)
            except (OSError,ProviderError): raise ProviderError('invalid_reference') from None
        payload={'model':c['model'],'prompt':prompt,'n':1,'size':f'{dimensions[0]}x{dimensions[1]}',
                 **c.get('extra_parameters',{})}
        if c.get('send_response_format',True): payload['response_format']=c.get('response_format','b64_json')
        if c.get('send_output_format',False): payload['output_format']=fmt
        headers={}
        if c.get('auth_type','bearer')=='bearer': headers['Authorization']='Bearer '+os.environ[c['api_key_env']]
        if c.get('idempotency_header'):
            if c['idempotency_header'] not in {'Idempotency-Key','X-Idempotency-Key'}: raise ProviderError('invalid_idempotency_header')
            headers[c['idempotency_header']]=request_id
        if blobs:
            boundary='geo'+uuid.uuid4().hex
            parts=[]
            for key,value in payload.items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'.encode()+str(value).encode('utf-8')+b'\r\n')
            for i,(blob,meta) in enumerate(zip(blobs,references)):
                field=c.get('edit_image_field','image')
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="reference_{i+1}.{meta["format"]}"\r\nContent-Type: image/{meta["format"]}\r\n\r\n'.encode()+blob+b'\r\n')
            parts.append(f'--{boundary}--\r\n'.encode())
            body=b''.join(parts); headers['Content-Type']='multipart/form-data; boundary='+boundary
            endpoint=c.get('edit_endpoint','/images/edits')
        else:
            body=json.dumps(payload,ensure_ascii=False).encode('utf-8'); headers['Content-Type']='application/json'
            endpoint=c.get('generation_endpoint','/images/generations')
        _,_,raw=self._request(c['base_url'].rstrip('/')+endpoint,'POST',body,headers)
        try:
            result=json.loads(raw)
            if not isinstance(result.get('data'),list) or len(result['data'])!=1: raise ValueError()
            item=result['data'][0]
            if item.get('b64_json'):
                data=base64.b64decode(item['b64_json'],validate=True)
            elif isinstance(item.get('url'),str): data=self._download(item['url'])
            else: raise ValueError()
        except ProviderError: raise
        except (ValueError,TypeError,KeyError,AttributeError): raise ProviderError('invalid_response') from None
        if len(data)>c.get('max_image_bytes',20*1024*1024): raise ProviderError('image_too_large')
        output_path.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.image-',suffix='.'+fmt,dir=output_path.parent)
        temp=Path(name)
        try:
            with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
            normalization=normalize_image_canvas(temp,dimensions,fmt)
            meta=validate_image(temp,dimensions,fmt)
            # link fails if another writer has already produced this file; never overwrite it.
            os.link(temp,output_path)
            meta['path']=str(output_path.resolve())
        except OSError: raise ProviderError('output_write_failed') from None
        finally: temp.unlink(missing_ok=True)
        usage=result.get('usage')
        safe_usage={k:v for k,v in usage.items() if isinstance(v,(int,float)) and not isinstance(v,bool)} if isinstance(usage,dict) else None
        result={**meta,'request_id':request_id,'status':'SUCCEEDED','references':references,
                'usage':safe_usage,'cost':None,'cost_status':'unknown','visual_review':'needs_review'}
        if normalization:result['normalization']=normalization
        return result
