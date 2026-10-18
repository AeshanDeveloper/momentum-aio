import logger from "@logger";

export default class PluginRegistry {
	async register (plugin){
		setTimeout(() => {
			logger.info("Registering plugin...")
		}, 200)
		return {
			success: true,
			isRegistered: true
		}
	}
	
	async unregister <Promise>(){
		return {
			success: true,
			isUnregistered: true
		}
	}
}