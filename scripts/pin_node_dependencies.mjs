import fs from 'node:fs'
import path from 'node:path'
for(const dir of ['frontend','infrastructure']){
  const file=path.join(dir,'package.json')
  const pkg=JSON.parse(fs.readFileSync(file,'utf8'))
  for(const section of ['dependencies','devDependencies'])for(const name of Object.keys(pkg[section]||{}))pkg[section][name]=JSON.parse(fs.readFileSync(path.join(dir,'node_modules',name,'package.json'),'utf8')).version
  fs.writeFileSync(file,JSON.stringify(pkg,null,2)+'\n')
}
