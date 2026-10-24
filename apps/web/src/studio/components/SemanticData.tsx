import type { ReactNode } from 'react'
const labels:Record<string,string>={models:'Modelos',workers:'Procesos de generación',qwen:'Qwen Imagen',h3:'MiniMax H3',yue2:'YuE Música',prompt:'Prompt',image_prompt:'Prompt de imagen',video_prompt:'Dirección de vídeo',model:'Modelo',status:'Estado',operation:'Operación',duration:'Duración',seconds:'Segundos',aspect_ratio:'Formato',width:'Ancho',height:'Alto',seed:'Semilla',quality:'Calidad',steps:'Pasos',mode:'Modo',chat:'Conversación',tools:'Herramientas',vision:'Visión',brief:'Concepto visual',lyrics:'Letra',sections:'Secciones',analysis:'Análisis de audio',bpm_estimate:'Ritmo estimado',start:'Inicio',end:'Fin',uri:'Archivo',sha256:'Huella del archivo',available:'Disponible',ready:'Preparado',enabled:'Habilitado',ok:'Estado correcto',kind:'Tipo',media:'Resultados',scene:'Escena',scenes:'Escenas'}
const safeText=(v:string)=>{try{const p=JSON.parse(v);if(p&&typeof p==='object')return p}catch{}return v}
const verbatim = (key:string,value:unknown) => typeof value==='string' && (key.includes('prompt') || ['brief','lyrics','content'].includes(key))
export function SemanticData({value,depth=0}:{value:unknown;depth?:number}):ReactNode {
 if(depth>6)return <span>Información adicional disponible en el resultado.</span>
 if(value==null)return <span className="muted">—</span>
 if(typeof value==='string'){const v=safeText(value);return v!==value?<SemanticData value={v} depth={depth+1}/>:<p className="semantic-text">{value}</p>}
 if(typeof value==='boolean')return <span>{value?'Sí':'No'}</span>
 if(typeof value==='number')return <span>{value}</span>
 if(Array.isArray(value))return value.length?<ol className="semantic-list">{value.map((v,i)=><li key={i}><SemanticData value={v} depth={depth+1}/></li>)}</ol>:<span className="muted">Sin elementos</span>
 if(typeof value==='object')return <dl className="data-fields">{Object.entries(value).filter(([k])=>!['api_key','password','encrypted_key','token','secret','base64','preview'].includes(k)).map(([k,v])=><div key={k}><dt>{labels[k]||k.replaceAll('_',' ').replace(/([a-z])([A-Z])/g,'$1 $2')}</dt><dd>{verbatim(k,v)?<p className="semantic-text">{v as string}</p>:<SemanticData value={v} depth={depth+1}/>}</dd></div>)}</dl>
 return null
}
