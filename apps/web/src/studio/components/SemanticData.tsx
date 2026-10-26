import type { ReactNode } from 'react'
import { t, type MessageKey } from '../../i18n'
const labels:Record<string,MessageKey|{raw:string}>={models:'shell.data.key.models',workers:'shell.data.key.workers',qwen:'shell.data.key.qwen',h3:{raw:'MiniMax H3'},yue2:'shell.data.key.yue2',prompt:{raw:'Prompt'},image_prompt:'shell.data.key.imagePrompt',video_prompt:'shell.data.key.videoPrompt',model:'shell.data.key.model',status:'shell.data.key.status',operation:'shell.data.key.operation',duration:'shell.data.key.duration',seconds:'shell.data.key.seconds',aspect_ratio:'shell.data.key.aspectRatio',width:'shell.data.key.width',height:'shell.data.key.height',seed:'shell.data.key.seed',quality:'shell.data.key.quality',steps:'shell.data.key.steps',mode:'shell.data.key.mode',chat:'shell.data.key.chat',tools:'shell.data.key.tools',vision:'shell.data.key.vision',brief:'shell.data.key.brief',lyrics:'shell.data.key.lyrics',sections:'shell.data.key.sections',analysis:'shell.data.key.analysis',bpm_estimate:'shell.data.key.bpmEstimate',start:'shell.data.key.start',end:'shell.data.key.end',uri:'shell.data.key.uri',sha256:'shell.data.key.sha256',available:'shell.data.key.available',ready:'shell.data.key.ready',enabled:'shell.data.key.enabled',ok:'shell.data.key.ok',kind:'shell.data.key.kind',media:'shell.data.key.media',scene:'shell.data.key.scene',scenes:'shell.data.key.scenes'}
const label=(k:string)=>{const l=labels[k];return typeof l==='string'?t(l):l?.raw}
const safeText=(v:string)=>{try{const p=JSON.parse(v);if(p&&typeof p==='object')return p}catch{}return v}
const verbatim = (key:string,value:unknown) => typeof value==='string' && (key.includes('prompt') || ['brief','lyrics','content'].includes(key))
export function SemanticData({value,depth=0}:{value:unknown;depth?:number}):ReactNode {
 if(depth>6)return <span>{t('shell.data.more')}</span>
 if(value==null)return <span className="muted">—</span>
 if(typeof value==='string'){const v=safeText(value);return v!==value?<SemanticData value={v} depth={depth+1}/>:<p className="semantic-text">{value}</p>}
 if(typeof value==='boolean')return <span>{value?t('shell.data.yes'):t('shell.data.no')}</span>
 if(typeof value==='number')return <span>{value}</span>
 if(Array.isArray(value))return value.length?<ol className="semantic-list">{value.map((v,i)=><li key={i}><SemanticData value={v} depth={depth+1}/></li>)}</ol>:<span className="muted">{t('shell.data.empty')}</span>
 if(typeof value==='object')return <dl className="data-fields">{Object.entries(value).filter(([k])=>!['api_key','password','encrypted_key','token','secret','base64','preview'].includes(k)).map(([k,v])=><div key={k}><dt>{label(k)||k.replaceAll('_',' ').replace(/([a-z])([A-Z])/g,'$1 $2')}</dt><dd>{verbatim(k,v)?<p className="semantic-text">{v as string}</p>:<SemanticData value={v} depth={depth+1}/>}</dd></div>)}</dl>
 return null
}
