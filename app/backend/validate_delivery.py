"""Read-only file consistency check; never imports collection or model clients."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import openpyxl


def contact(value):
    return str(value or '').strip()


def rows_signature(rows):
    return sorted((contact(r.get('主页身份ID') or r.get('identity') or r.get('id')), contact(r.get('微信')), contact(r.get('手机号')), contact(r.get('邮箱'))) for r in rows)


def queue_signature(rows):
    return sorted((contact(r.get('creator',{}).get('id')), contact(r.get('creator',{}).get('contact',{}).get('wechat')), contact(r.get('creator',{}).get('contact',{}).get('phone')), contact(r.get('creator',{}).get('contact',{}).get('email'))) for r in rows)


def validate(source):
    source=Path(source).resolve();delivery=json.loads(source.read_text(encoding='utf-8'))
    rows=delivery.get('rows',[]);declared=delivery.get('artifacts') or {};errors=[];files=[]
    def artifact(key,required=True):
        raw=declared.get(key)
        if not raw:
            if required:errors.append(f'{key}：未声明文件')
            return None
        file=Path(raw);file=file if file.is_absolute() else source.parent/file
        if not file.is_file():errors.append(f'{key}：文件不存在');return None
        return file
    def fingerprint(label,file):
        stat=file.stat();digest=hashlib.sha256()
        with file.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        files.append({'key':label,'path':str(file),'size':stat.st_size,'modified_ns':str(stat.st_mtime_ns),'sha256':digest.hexdigest()})
    fingerprint('finalJson',source)
    completion=delivery.get('contact_channel_completion') or {}
    baseline=completion.get('baseline_path')
    if baseline:
        baseline_file=Path(baseline)
        baseline_file=baseline_file if baseline_file.is_absolute() else source.parent/baseline_file
        if not baseline_file.is_file():errors.append('联系人渠道基线文件不存在，新增微信统计不可核对')
        else:fingerprint('contactCompletionBaseline',baseline_file)
    elif completion and (completion.get('baseline_available') is True or completion.get('new_wechat_count') is not None):
        errors.append('缺少联系人渠道基线，不能声明已核对新增微信数量')
    signature=rows_signature(rows)
    ids=[record[0] for record in signature]
    if any(not identity for identity in ids) or len(set(ids))!=len(ids):errors.append('最终 JSON：身份缺失或重复')
    seen=set()
    for record in signature:
        values={value.casefold() for value in record[1:] if value}
        if not values:errors.append('最终 JSON：存在没有明文联系方式的记录')
        if seen & values:errors.append('最终 JSON：跨达人联系方式重复')
        seen.update(values)
    standard=artifact('standardXlsx')
    if standard:
        workbook=openpyxl.load_workbook(standard,read_only=True,data_only=True)
        try:
            values=workbook.active.iter_rows(values_only=True);headers=next(values,())
            actual=[dict(zip(headers,row)) for row in values if any(v is not None for v in row)]
            if rows_signature(actual)!=signature:errors.append('标准 Excel 与最终 JSON 的身份或联系方式不一致')
        finally:workbook.close()
        fingerprint('standardXlsx',standard)
    expected=delivery.get('robot_queue',[])
    expected_signature=queue_signature(expected)
    queue_count=len(expected)
    if delivery.get('delivery_mode')!='contacts-only' and expected_signature!=signature:errors.append('最终 JSON 的待发送队列与名单不一致')
    if any(r.get('guardrails',{}).get('allowAutomaticSend') is not False for r in expected):errors.append('队列缺少禁止自动发送标记')
    for key in ['robotNdjson','robotBatchJson']:
        file=artifact(key)
        if not file:continue
        if key=='robotNdjson':records=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines() if line.strip()]
        else:
            batch=json.loads(file.read_text(encoding='utf-8'));records=batch.get('records',[])
            if batch.get('dryRunOnly') is not True:errors.append('机器人批量包未标记为仅预演')
        if queue_signature(records)!=expected_signature:errors.append(f'{key} 与保存队列的身份或联系方式不一致')
        if any(r.get('guardrails',{}).get('allowAutomaticSend') is not False for r in records):errors.append(f'{key} 缺少禁止自动发送标记')
        fingerprint(key,file)
    original=artifact('originalXlsx',False)
    if original:fingerprint('originalXlsx',original)
    manifest=artifact('handoffManifest')
    if manifest:
        handoff=json.loads(manifest.read_text(encoding='utf-8'));summary=handoff.get('summary',{})
        if summary.get('candidateCount')!=len(rows) or summary.get('robotRecordCount')!=queue_count:errors.append('交接清单人数与交付文件不一致')
        fingerprint('handoffManifest',manifest)
    return {'ok':not errors,'checkedAt':datetime.now(timezone.utc).isoformat(),'sourcePath':str(source),'rowCount':len(rows),'queueCount':queue_count,'errors':list(dict.fromkeys(errors)),'files':files,'sentVerified':False,'scope':'文件身份、明文联系方式、重复、发送保护；不判断达人适配准确率或联系方式可达性'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);args=parser.parse_args()
    try:result=validate(args.source)
    except Exception:result={'ok':False,'checkedAt':datetime.now(timezone.utc).isoformat(),'errors':['交付文件无法解析或读取，请核对文件格式及完整性'],'files':[]}
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
