export type TicketStatus = "open" | "closed" | "approved" | "rejected" | "processing" | "paid" | "canceled";
export type TicketType = "deposit" | "withdrawal" | "support" | "general";

export interface WithdrawalRequestItem {
	requestId: string;
	amount: number;
	reason?: string;
	requestedAt: Date;
}

export interface TicketRecord {
	_id?: string;
	ticketId: string;
	guildId: string;
	channelId?: string;
	messageId?: string;
	messageUrl?: string;
	requesterId: string;
	type: TicketType;
	status: TicketStatus;
	title: string;
	details?: {
		amount?: number;
		totalAmount?: number;
		currency?: string;
		reason?: string;
		transactionId?: string;
		reservedAmount?: number;
		requests?: WithdrawalRequestItem[];
		paidBy?: string;
		paidAt?: Date;
		canceledBy?: string;
		canceledAt?: Date;
		processedBy?: string;
		processedAt?: Date;
		note?: string;
		ltcAddress?: string | null;
		upiAddress?: string | null;
		[key: string]: any;
	};
	assignedStaffId?: string;
	closedBy?: string;
	closedAt?: Date;
	transcriptUrl?: string;
	createdAt: Date;
	updatedAt: Date;
}

export interface TicketGuildConfig {
	_id?: string;
	guildId: string;
	categoryId?: string;
	generalCategoryId?: string;
	withdrawalCategoryId?: string;
	transcriptChannelId?: string;
	staffRoleIds: string[];
	ticketManagerRoleIds?: string[];
	ticketManagerUserIds?: string[];
	minWithdrawalAmount: number;
	maxWithdrawalAmount?: number;
	maxActiveTicketsPerUser?: number;
	usersCanClose?: boolean;
	allowReopen?: boolean;
	transcriptsEnabled?: boolean;
	ticketCounter: number;
	enabled: boolean;
	updatedAt: Date;
}
