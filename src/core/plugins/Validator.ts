import logger from "@logger";

export default class PluginValidator {
	async validate (plugin = { id: null, link: null }){
		setTimeout(() => {
			logger.info("Validating plugin...")
		}, 200)
		return {
			success: true,
			isVerified: true
		}
	}
}