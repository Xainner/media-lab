import { useEffect, useRef, useState } from 'react'
import { Modal } from './ui'
const copy:Record<string,{title:string;description:string;yes:string;tone:string}>={
 'gallery-remove':{title:'Eliminar archivo',description:'Esta acción elimina el archivo de tu cuenta. Las referencias históricas pueden perder acceso. Los trabajos activos conservan sus archivos.',yes:'Eliminar mi archivo',tone:'danger'},
 'agent-clear':{title:'Una nueva conversación',description:'El historial permanece guardado. Los trabajos autorizados siguen su curso.',yes:'Abrir conversación',tone:'primary'},
 'character-remove':{title:'Borrar personaje',description:'Se borra el @nombre y su ficha. Sus fotos siguen en tu biblioteca y lo ya creado no cambia.',yes:'Borrar personaje',tone:'danger'},
 'lora-remove':{title:'Quitar LoRA',description:'Se quita de tu biblioteca y de los personajes que lo usan. Puedes volver a añadirlo con el mismo enlace.',yes:'Quitar LoRA',tone:'danger'},
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
 return <Modal open={!!request} onOpenChange={open=>{if(!open)finish(false)}} title={text.title} description={text.description}><div className="button-row"><button onClick={()=>finish(false)}>Volver</button><button className={text.tone} onClick={()=>finish(true)}>{text.yes}</button></div></Modal>
}
