import { useEffect, useRef, useState } from 'react'
import { Modal } from './ui'
import { t, type MessageKey } from './i18n'
// Keys, not text: the dialog translates at render so it follows the current language.
const copy:Record<string,{title:MessageKey;description:MessageKey;yes:MessageKey;tone:string}>={
 'gallery-remove':{title:'connect.confirm.galleryRemove.title',description:'connect.confirm.galleryRemove.description',yes:'connect.confirm.galleryRemove.yes',tone:'danger'},
 'agent-clear':{title:'connect.confirm.agentClear.title',description:'connect.confirm.agentClear.description',yes:'connect.confirm.agentClear.yes',tone:'primary'},
 'character-remove':{title:'connect.confirm.characterRemove.title',description:'connect.confirm.characterRemove.description',yes:'connect.confirm.characterRemove.yes',tone:'danger'},
 'lora-remove':{title:'connect.confirm.loraRemove.title',description:'connect.confirm.loraRemove.description',yes:'connect.confirm.loraRemove.yes',tone:'danger'},
}
export default function Confirm() {
 const [request,setRequest] = useState<{action:string;resolve:(value:boolean)=>void}|null>(null)
 const pending = useRef<typeof request>(null)
 useEffect(()=>{
  const receive=(e:Event)=>{pending.current?.resolve(false);pending.current=(e as CustomEvent).detail;setRequest(pending.current)}
  window.addEventListener('rvl-confirm',receive)
  return()=>{window.removeEventListener('rvl-confirm',receive);pending.current?.resolve(false)}
 },[])
 function finish(value:boolean){pending.current?.resolve(value);pending.current=null;setRequest(null)}
 const text=copy[request?.action||'']||copy['gallery-remove']
 return <Modal open={!!request} onOpenChange={open=>{if(!open)finish(false)}} title={t(text.title)} description={t(text.description)}><div className="button-row"><button onClick={()=>finish(false)}>{t('connect.confirm.back')}</button><button className={text.tone} onClick={()=>finish(true)}>{t(text.yes)}</button></div></Modal>
}
