import logger from "@logger";

export default class PluginLoader {
	async load (plugin = { link: null, id: null }){
		setTimeout(() => {
			logger.info("Loading plugin...")
		}, 200)
		return {
			success: true,
			error: false,
			isLoaded: true
		}
	}
	
	async unload (plugin = {id: null, link: null}){
		
		setTimeout(() => {
			logger.info("Unloading plugin...")
		}, 200)
		return {
			success: true,
			error: false,
			isLoaded: true
		}
	}
}